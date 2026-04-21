from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import tomllib


APP_NAME = "openpalm"


@dataclass(slots=True)
class AppConfig:
    base_dir: Path
    session_dir: Path
    state_file: Path
    dedup_file: Path
    log_file: Path
    shell: str = "/bin/zsh"
    working_dir: Path = Path.home()
    command_timeout_seconds: int = 20
    max_output_chars: int = 3500
    reply_on_empty_output: bool = True


def default_base_dir() -> Path:
    env_path = os.getenv("WHATS_SHELL_AGENT_BASE_DIR")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".config" / APP_NAME


def config_file_path() -> Path:
    return default_base_dir() / "config.toml"


def default_config() -> AppConfig:
    base = default_base_dir()
    return AppConfig(
        base_dir=base,
        session_dir=base / "session",
        state_file=base / "state.json",
        dedup_file=base / "processed_messages.json",
        log_file=base / "app.log",
        working_dir=Path.home(),
    )


def ensure_dirs(cfg: AppConfig) -> None:
    try:
        cfg.base_dir.mkdir(parents=True, exist_ok=True)
        cfg.session_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fallback = Path.home() / ".openpalm"
        cfg.base_dir = fallback
        cfg.session_dir = fallback / "session"
        cfg.state_file = fallback / "state.json"
        cfg.dedup_file = fallback / "processed_messages.json"
        cfg.log_file = fallback / "app.log"
        cfg.base_dir.mkdir(parents=True, exist_ok=True)
        cfg.session_dir.mkdir(parents=True, exist_ok=True)


def _to_toml_text(cfg: AppConfig) -> str:
    data = asdict(cfg)
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, Path):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f'{key} = "{value}"')
    return "\n".join(lines) + "\n"


def load_config() -> AppConfig:
    path = config_file_path()
    if not path.exists():
        cfg = default_config()
        ensure_dirs(cfg)
        effective_path = cfg.base_dir / "config.toml"
        effective_path.write_text(_to_toml_text(cfg), encoding="utf-8")
        return cfg

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = default_config()

    cfg.base_dir = Path(str(raw.get("base_dir", cfg.base_dir))).expanduser()
    cfg.session_dir = Path(str(raw.get("session_dir", cfg.session_dir))).expanduser()
    cfg.state_file = Path(str(raw.get("state_file", cfg.state_file))).expanduser()
    cfg.dedup_file = Path(str(raw.get("dedup_file", cfg.dedup_file))).expanduser()
    cfg.log_file = Path(str(raw.get("log_file", cfg.log_file))).expanduser()
    cfg.shell = str(raw.get("shell", cfg.shell))
    cfg.working_dir = Path(str(raw.get("working_dir", cfg.working_dir))).expanduser()
    cfg.command_timeout_seconds = int(raw.get("command_timeout_seconds", cfg.command_timeout_seconds))
    cfg.max_output_chars = int(raw.get("max_output_chars", cfg.max_output_chars))
    cfg.reply_on_empty_output = bool(raw.get("reply_on_empty_output", cfg.reply_on_empty_output))

    ensure_dirs(cfg)
    return cfg
