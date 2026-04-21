from __future__ import annotations

from openpalm.config import AppConfig
from openpalm.models import CommandResult


def format_command_reply(result: CommandResult, cfg: AppConfig) -> str:
    header = f"$ {result.command}\n"

    if result.timed_out:
        base = f"{header}\nError: command exceeded timeout of {cfg.command_timeout_seconds}s."
        return base + _trunc_note(result.truncated)

    lines: list[str] = [header]
    if result.stdout.strip():
        lines.append(result.stdout.rstrip())
    if result.stderr.strip():
        if result.exit_code and result.exit_code != 0:
            lines.append(f"Exit code: {result.exit_code}")
        lines.append(result.stderr.rstrip())

    if not result.stdout.strip() and not result.stderr.strip() and cfg.reply_on_empty_output:
        lines.append("Command executed with no output.")

    if result.exit_code and result.exit_code != 0 and not result.stderr.strip():
        lines.append(f"Exit code: {result.exit_code}")

    msg = "\n\n".join(lines).strip()
    return msg + _trunc_note(result.truncated)


def format_enabled_reply() -> str:
    return "AI mode enabled."


def format_disabled_reply() -> str:
    return "AI mode disabled."


def _trunc_note(truncated: bool) -> str:
    return "\n\n[Output was truncated by configured limit.]" if truncated else ""
