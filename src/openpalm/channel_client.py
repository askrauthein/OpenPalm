from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from openpalm.models import IncomingMessage

logger = logging.getLogger(__name__)


class ChannelClient(Protocol):
    def ensure_authenticated(self, reset_session: bool = False) -> None: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def own_jid(self) -> str: ...

    def on_text_message(self, handler: Callable[[IncomingMessage], None]) -> None: ...

    def send_text(self, to_jid: str, text: str) -> None: ...

    def run_forever(self) -> None: ...


class NeonizeClientAdapter:
    def __init__(self, session_dir: str) -> None:
        self.session_dir = Path(session_dir)
        self._handler: Callable[[IncomingMessage], None] | None = None
        self._own_jid = "self@wa"
        self._neonize_import_error: str | None = None
        self._running = False
        self._connect_thread: threading.Thread | None = None
        self._connect_error: Exception | None = None

        self._client: Any | None = None
        self._jid_mod: Any | None = None
        self._jid_cls: Any | None = None
        self._events_map: dict[Any, int] = {}
        self._jid_cache: dict[str, Any] = {}
        self._event_message_cls: Any | None = None
        self._event_connected_cls: Any | None = None
        self._event_disconnected_cls: Any | None = None

        try:
            import neonize
            from neonize.events import EVENT_TO_INT
            from neonize.proto import Neonize_pb2
            from neonize.utils import jid

            self._neonize = neonize
            self._events_map = EVENT_TO_INT
            self._jid_mod = jid
            self._jid_cls = Neonize_pb2.JID
            self._event_message_cls = self._event_cls_for_code(17)
            self._event_connected_cls = self._event_cls_for_code(3)
            self._event_disconnected_cls = self._event_cls_for_code(12)
            self._neonize_available = True
        except Exception as exc:  # noqa: BLE001
            self._neonize_available = False
            self._neonize_import_error = str(exc)

    def ensure_authenticated(self, reset_session: bool = False) -> None:
        self._require_neonize()
        if reset_session and self.session_dir.exists():
            logger.info("Session reset at %s", self.session_dir)
        self._init_client()
        logger.info("Authentication ready. If no session exists, QR will be shown on connect.")

    def connect(self) -> None:
        self._require_neonize()
        self._init_client()

        if self._connect_thread and self._connect_thread.is_alive():
            logger.info("Conexao ja em andamento.")
            return

        self._running = True
        self._connect_error = None
        self._connect_thread = threading.Thread(target=self._connect_worker, daemon=True)
        self._connect_thread.start()
        logger.info("WhatsApp connection started.")

    def disconnect(self) -> None:
        self._running = False
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to disconnect client.")
        logger.info("Client disconnected.")

    def own_jid(self) -> str:
        return self._own_jid

    def on_text_message(self, handler: Callable[[IncomingMessage], None]) -> None:
        self._handler = handler

    def send_text(self, to_jid: str, text: str) -> None:
        self._require_neonize()
        self._init_client()
        try:
            self._client.send_message(self._jid_for_send(to_jid), text)
            logger.info("Reply sent to %s (%s chars)", to_jid, len(text))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send reply to %s", to_jid)
            raise

    def run_forever(self) -> None:
        self._require_neonize()
        while self._running:
            if self._connect_error is not None:
                raise RuntimeError(f"Neonize connection failure: {self._connect_error}") from self._connect_error
            if self._connect_thread and not self._connect_thread.is_alive():
                # Algumas versoes podem retornar imediatamente; mantemos loop ativo.
                time.sleep(0.5)
            time.sleep(0.5)

    def _connect_worker(self) -> None:
        assert self._client is not None
        try:
            self._client.connect()
            # Se connect() retornar (dependendo da versao), mantemos processo vivo.
            while self._running:
                time.sleep(1)
        except Exception as exc:  # noqa: BLE001
            self._connect_error = exc
            self._running = False
            logger.exception("Neonize connection error.")

    def _init_client(self) -> None:
        if self._client is not None:
            return

        self.session_dir.mkdir(parents=True, exist_ok=True)
        client_name = str(self.session_dir / "session")
        self._client = self._neonize.NewClient(client_name)
        self._bind_callbacks()

    def _bind_callbacks(self) -> None:
        assert self._client is not None
        assert self._event_message_cls is not None

        # QR no terminal.
        self._client.qr(self._on_qr)

        @self._client.event(self._event_message_cls)
        def _on_message(_: Any, event: Any) -> None:
            self._handle_message_event(event)

        if self._event_connected_cls is not None:
            @self._client.event(self._event_connected_cls)
            def _on_connected(_: Any, __: Any) -> None:
                logger.info("WhatsApp connected.")
                self._refresh_own_jid()

        if self._event_disconnected_cls is not None:
            @self._client.event(self._event_disconnected_cls)
            def _on_disconnected(_: Any, __: Any) -> None:
                logger.warning("WhatsApp disconnected.")

    def _on_qr(self, _: Any, data_qr: bytes) -> None:
        try:
            import segno

            logger.info("QR code received. Scan in WhatsApp > Linked devices.")
            segno.make_qr(data_qr.decode("utf-8", errors="ignore")).terminal(compact=True)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to render QR code in terminal.")

    def _handle_message_event(self, event: Any) -> None:
        if self._handler is None:
            return

        incoming = self._event_to_incoming_message(event)
        if incoming is None:
            return
        self._handler(incoming)

    def _event_to_incoming_message(self, event: Any) -> IncomingMessage | None:
        try:
            info = event.Info
            source = info.MessageSource

            text = self._extract_text(event.Message)
            msg_type = "text" if text is not None else "non_text"

            from_jid = self._jid_mod.Jid2String(self._jid_mod.JIDToNonAD(source.Sender))
            to_jid = self._jid_mod.Jid2String(self._jid_mod.JIDToNonAD(source.Chat))
            if not to_jid:
                to_jid = from_jid
            self._cache_jid(from_jid, source.Sender)
            self._cache_jid(to_jid, source.Chat)

            ts_raw = int(info.Timestamp)
            timestamp = self._timestamp_from_raw(ts_raw)
            message_id = str(info.ID or f"msg-{ts_raw}")
            from_me = bool(source.IsFromMe)

            return IncomingMessage(
                message_id=message_id,
                from_jid=from_jid,
                to_jid=to_jid,
                text=text,
                timestamp=timestamp,
                message_type=msg_type,
                from_me=from_me,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to convert message event.")
            return None

    def _extract_text(self, msg: Any) -> str | None:
        if msg is None:
            return None

        conversation = getattr(msg, "conversation", "")
        if conversation:
            return str(conversation)

        if hasattr(msg, "extendedTextMessage") and msg.HasField("extendedTextMessage"):
            text = getattr(msg.extendedTextMessage, "text", "")
            if text:
                return str(text)

        # wrappers comuns no WhatsApp
        for wrapper_field in (
            "ephemeralMessage",
            "viewOnceMessage",
            "viewOnceMessageV2",
            "viewOnceMessageV2Extension",
            "editedMessage",
        ):
            if hasattr(msg, wrapper_field) and msg.HasField(wrapper_field):
                wrapper = getattr(msg, wrapper_field)
                inner = getattr(wrapper, "message", None)
                if inner is not None:
                    found = self._extract_text(inner)
                    if found:
                        return found

        return None

    def _refresh_own_jid(self) -> None:
        try:
            device = self._client.get_me()
            if hasattr(device, "JID"):
                self._own_jid = self._jid_mod.Jid2String(self._jid_mod.JIDToNonAD(device.JID))
                logger.info("Authenticated JID: %s", self._own_jid)
        except Exception:  # noqa: BLE001
            logger.exception("Could not fetch authenticated JID.")

    def _jid_from_string(self, raw: str) -> Any:
        if "@" in raw:
            user, server = raw.split("@", 1)
            return self._jid_cls(
                User=user,
                RawAgent=0,
                Device=0,
                Integrator=0,
                Server=server,
                IsEmpty=False,
            )
        return self._jid_mod.build_jid(raw)

    def _jid_for_send(self, raw: str) -> Any:
        cached = self._jid_cache.get(raw)
        if cached is not None:
            return cached
        return self._jid_from_string(raw)

    def _cache_jid(self, key: str, jid_obj: Any) -> None:
        try:
            copied = self._jid_cls()
            copied.CopyFrom(jid_obj)
            self._jid_cache[key] = copied
        except Exception:  # noqa: BLE001
            logger.exception("Failed to cache JID %s", key)

    def _event_cls_for_code(self, code: int) -> Any | None:
        for cls, event_code in self._events_map.items():
            if event_code == code:
                return cls
        return None

    def _timestamp_from_raw(self, raw: int) -> datetime:
        # Compatibilidade com segundos, ms e ns.
        if raw > 10_000_000_000_000_000:
            return datetime.fromtimestamp(raw / 1_000_000_000, tz=timezone.utc)
        if raw > 10_000_000_000_000:
            return datetime.fromtimestamp(raw / 1_000_000, tz=timezone.utc)
        if raw > 10_000_000_000:
            return datetime.fromtimestamp(raw / 1_000, tz=timezone.utc)
        return datetime.fromtimestamp(raw, tz=timezone.utc)

    def _require_neonize(self) -> None:
        if not self._neonize_available:
            detail = f" Reason: {self._neonize_import_error}" if self._neonize_import_error else ""
            raise RuntimeError(f"neonize is not available in the current environment.{detail}")
