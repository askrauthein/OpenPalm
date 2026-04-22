from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import tomllib

from openpalm.agent_models import Project


class ProjectRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list_projects(self) -> list[Project]:
        return sorted(self._load().values(), key=lambda p: p.project_id)

    def get(self, project_id: str) -> Project | None:
        return self._load().get(project_id)

    def add(self, project: Project) -> None:
        data = self._load()
        if project.project_id in data:
            raise ValueError(f"Project alias already exists: {project.project_id}")
        data[project.project_id] = project
        self._save(data)

    def remove(self, project_id: str) -> None:
        data = self._load()
        if project_id not in data:
            raise ValueError(f"Project not found: {project_id}")
        del data[project_id]
        self._save(data)

    def _load(self) -> dict[str, Project]:
        if not self.path.exists():
            return {}
        raw = tomllib.loads(self.path.read_text(encoding="utf-8"))
        projects_raw = raw.get("projects", {})
        result: dict[str, Project] = {}
        for pid, payload in projects_raw.items():
            result[pid] = Project(
                project_id=pid,
                source_type=str(payload.get("source_type", "local")),
                path=_to_none(payload.get("path")),
                repo=_to_none(payload.get("repo")),
                clone_url=_to_none(payload.get("clone_url")),
                git_remote=_to_none(payload.get("git_remote")),
                default_branch=str(payload.get("default_branch", "main")),
                marker_file=str(payload.get("marker_file", ".project-agent.toml")),
                allowed_agents=list(payload.get("allowed_agents", ["codex", "claude-code"])),
                enabled=bool(payload.get("enabled", True)),
            )
        return result

    def _save(self, data: dict[str, Project]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["[projects]"]
        for pid in sorted(data):
            p = data[pid]
            lines.append("")
            lines.append(f"[projects.{pid}]")
            for key, value in asdict(p).items():
                if key == "project_id":
                    continue
                lines.append(_toml_line(key, value))
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_line(key: str, value: object) -> str:
    if value is None:
        return f"{key} = \"\""
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    if isinstance(value, list):
        rendered = ", ".join(f'\"{str(v)}\"' for v in value)
        return f"{key} = [{rendered}]"
    return f'{key} = "{str(value)}"'


def _to_none(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
