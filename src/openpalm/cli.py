from __future__ import annotations

import argparse
import logging
import shutil
import time

from openpalm.app import OpenPalmApp
from openpalm.command_state import CommandStateManager
from openpalm.config import load_config
from openpalm.logging_config import setup_logging
from openpalm.storage import JsonStorage, ProcessedMessageStore
from openpalm.channel_client import NeonizeClientAdapter

logger = logging.getLogger(__name__)


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config()
    setup_logging(cfg)

    wa_client = NeonizeClientAdapter(session_dir=str(cfg.session_dir))
    wa_client.ensure_authenticated(reset_session=False)

    state_manager = CommandStateManager(JsonStorage(cfg.state_file))
    dedup_store = ProcessedMessageStore(cfg.dedup_file)

    app = OpenPalmApp(
        cfg=cfg,
        wa_client=wa_client,
        state_manager=state_manager,
        dedup_store=dedup_store,
    )
    app.run()
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    cfg = load_config()
    setup_logging(cfg)

    if args.reset_session and cfg.session_dir.exists():
        shutil.rmtree(cfg.session_dir, ignore_errors=True)
        cfg.session_dir.mkdir(parents=True, exist_ok=True)

    wa_client = NeonizeClientAdapter(session_dir=str(cfg.session_dir))
    wa_client.ensure_authenticated(reset_session=args.reset_session)
    wa_client.connect()

    print("Login started. Scan the QR code in your terminal.")
    print("Waiting for authentication... (Ctrl+C to exit)")
    started = time.time()
    while time.time() - started < 180:
        if wa_client.own_jid() != "self@wa":
            print(f"Authenticated as: {wa_client.own_jid()}")
            wa_client.disconnect()
            return 0
        time.sleep(0.5)

    print("Authentication timeout reached (180s). Please try again.")
    wa_client.disconnect()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config()
    state = CommandStateManager(JsonStorage(cfg.state_file)).load()

    print(f"base_dir: {cfg.base_dir}")
    print(f"session_dir: {cfg.session_dir} (exists={cfg.session_dir.exists()})")
    print(f"interpreter_enabled: {state.command_interpreter_enabled}")
    print(f"log_file: {cfg.log_file}")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    cfg = load_config()
    if cfg.session_dir.exists():
        shutil.rmtree(cfg.session_dir, ignore_errors=True)
    CommandStateManager(JsonStorage(cfg.state_file)).set_enabled(False)
    print("Session removed and interpreter disabled.")
    return 0


def cmd_projectbox(args: argparse.Namespace) -> int:
    from openpalm.agent_config import load_agent_paths
    from openpalm.agent_state import AgentStateStore
    from pathlib import Path

    paths = load_agent_paths()
    store = AgentStateStore(paths.state_file)
    state = store.load()

    if args.path:
        new_box = str(Path(args.path).expanduser())
        state.project_box = new_box
        store.save(state)
        print(f"Project Box set to: {new_box}")
    else:
        current = state.project_box or "~/openpalm-projects"
        print(f"Current Project Box: {current}")
    return 0


def cmd_help(args: argparse.Namespace) -> int:
    build_parser().print_help()
    return 0



def cmd_chat(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone
    from openpalm.models import IncomingMessage
    from openpalm.app import OpenPalmApp

    cfg = load_config()
    setup_logging(cfg)

    class CommandLineClientAdapter:
        def __init__(self, message: str | None = None):
            self._handler = None
            self._message = message
            self._running = False

        def ensure_authenticated(self, reset_session: bool = False) -> None:
            pass

        def connect(self) -> None:
            pass

        def disconnect(self) -> None:
            pass

        def own_jid(self) -> str:
            return "cli@localhost"

        def on_text_message(self, handler) -> None:
            self._handler = handler

        def send_text(self, to_jid: str, text: str) -> None:
            print(f"\n[OpenPalm]\n{text}")

        def run_forever(self) -> None:
            self._running = True
            if self._message is not None:
                if self._handler:
                    msg = IncomingMessage(
                        message_id=f"cli-{time.time()}",
                        from_jid="user@localhost",
                        to_jid="cli@localhost",
                        text=self._message,
                        timestamp=datetime.now(timezone.utc),
                        message_type="text",
                        from_me=True
                    )
                    self._handler(msg)
                return

            print("OpenPalm CLI Chat (Ctrl+C or 'exit' to quit)")
            try:
                msg_id = 1
                while self._running:
                    text = input("\n[You]> ")
                    if text.strip().lower() in ("exit", "quit"):
                        break
                    if not text.strip():
                        continue
                    if self._handler:
                        msg = IncomingMessage(
                            message_id=f"cli-loop-{msg_id}-{time.time()}",
                            from_jid="user@localhost",
                            to_jid="cli@localhost",
                            text=text,
                            timestamp=datetime.now(timezone.utc),
                            message_type="text",
                            from_me=True
                        )
                        self._handler(msg)
                        msg_id += 1
            except (KeyboardInterrupt, EOFError):
                print()

    wa_client = CommandLineClientAdapter(message=args.message)
    state_manager = CommandStateManager(JsonStorage(cfg.state_file))
    dedup_store = ProcessedMessageStore(cfg.dedup_file)

    app = OpenPalmApp(
        cfg=cfg,
        wa_client=wa_client,  # type: ignore
        state_manager=state_manager,
        dedup_store=dedup_store,
    )
    app.run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openpalm")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Start the agent listener")
    p_run.set_defaults(func=cmd_run)

    p_login = sub.add_parser("login", help="Start WhatsApp login/pairing")
    p_login.add_argument("--reset-session", action="store_true", help="Remove local session before login")
    p_login.set_defaults(func=cmd_login)

    p_status = sub.add_parser("status", help="Show local status")
    p_status.set_defaults(func=cmd_status)

    p_logout = sub.add_parser("logout", help="Remove local session")
    p_logout.set_defaults(func=cmd_logout)

    p_box = sub.add_parser("projectbox", help="View or set the Project Box directory")
    p_box.add_argument("path", nargs="?", help="New path for the Project Box")
    p_box.set_defaults(func=cmd_projectbox)

    p_help = sub.add_parser("help", help="Show this help message")
    p_help.set_defaults(func=cmd_help)

    p_chat = sub.add_parser("chat", help="Send a message to openpalm directly from the CLI or start an interactive chat")
    p_chat.add_argument("message", nargs="?", help="Message to send (optional)")
    p_chat.set_defaults(func=cmd_chat)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        exit_code = args.func(args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("fatal error")
        print(f"Error: {exc}")
        exit_code = 1
    raise SystemExit(exit_code)
