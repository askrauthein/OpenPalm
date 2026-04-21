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
