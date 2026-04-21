from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import sys

from openpalm.command_executor import CommandExecutor
from openpalm.command_state import CommandStateManager
from openpalm.config import AppConfig
from openpalm.formatter import format_command_reply, format_disabled_reply, format_enabled_reply
from openpalm.message_filter import MessageFilter
from openpalm.models import IncomingMessage
from openpalm.storage import ProcessedMessageStore
from openpalm.channel_client import ChannelClient
from openpalm.agent_service import AgentService

logger = logging.getLogger(__name__)


class OpenPalmApp:
    def __init__(
        self,
        cfg: AppConfig,
        wa_client: ChannelClient,
        state_manager: CommandStateManager,
        dedup_store: ProcessedMessageStore,
    ) -> None:
        self.cfg = cfg
        self.wa_client = wa_client
        self.state_manager = state_manager
        self.dedup_store = dedup_store

        self._state = self.state_manager.load()
        self._filter = MessageFilter(own_jid=self.wa_client.own_jid())
        self._executor = CommandExecutor(
            shell=cfg.shell,
            working_dir=str(cfg.working_dir),
            timeout_seconds=cfg.command_timeout_seconds,
            max_output_chars=cfg.max_output_chars,
        )
        self._reply_jid: str | None = None
        self._agent_service = AgentService(notify=self._notify_job_event)

    def run(self) -> None:
        logger.info("startup")
        self.wa_client.on_text_message(self._handle_incoming)
        self.wa_client.connect()
        logger.info("LISTENING")
        self.wa_client.run_forever()

    def _handle_incoming(self, msg: IncomingMessage) -> None:
        logger.info("message received id=%s", msg.message_id)
        self._filter.own_jid = self.wa_client.own_jid()

        if self.dedup_store.has(msg.message_id):
            logger.info("message ignored (duplicate) id=%s", msg.message_id)
            return

        filter_reason = self._filter.validation_reason(msg)
        if filter_reason is not None:
            logger.info(
                "message ignored (filter=%s from=%s to=%s from_me=%s type=%s)",
                filter_reason,
                msg.from_jid,
                msg.to_jid,
                msg.from_me,
                msg.message_type,
            )
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        text = (msg.text or "").strip()
        if text == "/help":
            if self._state.command_interpreter_enabled:
                for chunk in self._read_help_chunks():
                    self.wa_client.send_text(msg.to_jid, chunk)
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return
        if text.startswith("/say "):
            phrase = text[len("/say ") :].strip()
            if not phrase:
                self.wa_client.send_text(msg.to_jid, "Usage: /say <text>")
                self.dedup_store.add(msg.message_id, msg.timestamp)
                return
            if sys.platform != "darwin":
                self.wa_client.send_text(msg.to_jid, "The /say command is only supported on macOS.")
                self.dedup_store.add(msg.message_id, msg.timestamp)
                return
            try:
                cp = subprocess.run(
                    ["say", "-v", "Luciana", phrase],
                    capture_output=True,
                    text=True,
                )
                if cp.returncode == 0:
                    self.wa_client.send_text(msg.to_jid, "Speech played with voice Luciana.")
                else:
                    stderr = (cp.stderr or "").strip()
                    self.wa_client.send_text(
                        msg.to_jid,
                        f"Failed to run /say (exit code {cp.returncode}).{(' ' + stderr[:300]) if stderr else ''}",
                    )
            except Exception as exc:  # noqa: BLE001
                self.wa_client.send_text(msg.to_jid, f"Failed to run /say: {exc}")
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        if text == "/status":
            self._reply_jid = msg.to_jid
            command_result = self._agent_service.handle_text(text)
            if command_result.handled and command_result.reply:
                self.wa_client.send_text(msg.to_jid, command_result.reply)
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        if text == "/tokens":
            self._reply_jid = msg.to_jid
            command_result = self._agent_service.handle_text(text)
            if command_result.handled and command_result.reply:
                self.wa_client.send_text(msg.to_jid, command_result.reply)
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        if text == "/ask" or text.startswith(("/project ", "/agent ", "/task ", "/job ", "/ask ")):
            self._reply_jid = msg.to_jid
            command_result = self._agent_service.handle_text(text)
            if command_result.handled:
                if command_result.reply:
                    self.wa_client.send_text(msg.to_jid, command_result.reply)
                self.dedup_store.add(msg.message_id, msg.timestamp)
                return
        if text == "/ai enable":
            self._state = self.state_manager.set_enabled(True)
            logger.info("control command: enable")
            self.wa_client.send_text(msg.to_jid, format_enabled_reply())
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        if text == "/ai disable":
            self._state = self.state_manager.set_enabled(False)
            logger.info("control command: disable")
            self.wa_client.send_text(msg.to_jid, format_disabled_reply())
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        if not self._state.command_interpreter_enabled:
            logger.info("message ignored (interpreter disabled)")
            self.dedup_store.add(msg.message_id, msg.timestamp)
            return

        logger.info("command execution started")
        result = self._executor.execute(text)
        logger.info(
            "command execution finished exit=%s timed_out=%s duration_ms=%s",
            result.exit_code,
            result.timed_out,
            result.duration_ms,
        )

        response = format_command_reply(result, self.cfg)
        self.wa_client.send_text(msg.to_jid, response)
        self.dedup_store.add(msg.message_id, msg.timestamp)

    def _notify_job_event(self, text: str) -> None:
        if not self._reply_jid:
            return
        try:
            self.wa_client.send_text(self._reply_jid, text)
        except Exception:  # noqa: BLE001
            logger.exception("failed to send async job notification")

    def _read_help_chunks(self, chunk_size: int = 3000) -> list[str]:
        help_path = Path(__file__).resolve().parents[2] / "help.txt"
        if not help_path.exists():
            return ["Help file not found."]
        content = help_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return ["Help file is empty."]
        return [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
