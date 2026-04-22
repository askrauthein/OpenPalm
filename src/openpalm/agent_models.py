from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


SourceType = Literal["local", "github"]
JobStatus = Literal[
    "queued",
    "preparing_project",
    "validating_project",
    "creating_workspace",
    "starting_agent",
    "running",
    "awaiting_input",
    "collecting_results",
    "succeeded",
    "failed",
    "cancelled",
]


@dataclass(slots=True)
class Project:
    project_id: str
    source_type: SourceType
    path: str | None
    repo: str | None
    clone_url: str | None
    git_remote: str | None
    default_branch: str
    marker_file: str
    allowed_agents: list[str]
    enabled: bool = True


@dataclass(slots=True)
class AgentRuntimeState:
    project_box: str | None = None
    current_project: str | None = None
    current_agent: str = "codex"
    agent_mode_enabled: bool = True
    allow_parallel_jobs: bool = False


@dataclass(slots=True)
class Job:
    job_id: str
    project_id: str
    agent: str
    instruction: str
    base_ref: str
    workspace_path: str
    work_branch: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result_summary: str | None = None
    error_message: str | None = None
    cancelled: bool = False
