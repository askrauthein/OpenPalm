from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class AgentPaths:
    config_dir: Path
    cache_dir: Path
    projects_file: Path
    state_file: Path
    jobs_db: Path
    logs_dir: Path
    repos_dir: Path
    jobs_dir: Path


def load_agent_paths() -> AgentPaths:
    base_config = Path(os.getenv("OPENPALM_AGENT_CONFIG_DIR", str(Path.home() / ".config" / "whats-agent"))).expanduser()
    base_cache = Path(os.getenv("OPENPALM_AGENT_CACHE_DIR", str(Path.home() / ".cache" / "whats-agent"))).expanduser()
    paths = AgentPaths(
        config_dir=base_config,
        cache_dir=base_cache,
        projects_file=base_config / "projects.toml",
        state_file=base_config / "state.json",
        jobs_db=base_config / "jobs.db",
        logs_dir=base_config / "logs",
        repos_dir=base_cache / "repos",
        jobs_dir=base_cache / "jobs",
    )
    paths = ensure_agent_dirs(paths)
    return paths


def ensure_agent_dirs(paths: AgentPaths) -> AgentPaths:
    try:
        for p in (paths.config_dir, paths.cache_dir, paths.logs_dir, paths.repos_dir, paths.jobs_dir):
            p.mkdir(parents=True, exist_ok=True)
        return paths
    except PermissionError:
        fallback_root = Path.home() / ".openpalm" / "whats-agent"
        fallback = AgentPaths(
            config_dir=fallback_root / "config",
            cache_dir=fallback_root / "cache",
            projects_file=fallback_root / "config" / "projects.toml",
            state_file=fallback_root / "config" / "state.json",
            jobs_db=fallback_root / "config" / "jobs.db",
            logs_dir=fallback_root / "config" / "logs",
            repos_dir=fallback_root / "cache" / "repos",
            jobs_dir=fallback_root / "cache" / "jobs",
        )
        for p in (fallback.config_dir, fallback.cache_dir, fallback.logs_dir, fallback.repos_dir, fallback.jobs_dir):
            p.mkdir(parents=True, exist_ok=True)
        return fallback
