from __future__ import annotations

import json
from pathlib import Path

from openpalm.agent_models import AgentRuntimeState


class AgentStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AgentRuntimeState:
        if not self.path.exists():
            return AgentRuntimeState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return AgentRuntimeState(
            project_box=raw.get("project_box"),
            current_project=raw.get("current_project"),
            current_agent=str(raw.get("current_agent", "codex")),
            agent_mode_enabled=bool(raw.get("agent_mode_enabled", True)),
            allow_parallel_jobs=bool(raw.get("allow_parallel_jobs", False)),
        )

    def save(self, state: AgentRuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "project_box": state.project_box,
                    "current_project": state.current_project,
                    "current_agent": state.current_agent,
                    "agent_mode_enabled": state.agent_mode_enabled,
                    "allow_parallel_jobs": state.allow_parallel_jobs,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
