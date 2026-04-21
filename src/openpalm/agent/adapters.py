from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Protocol


@dataclass(slots=True)
class AgentRunResult:
    exit_code: int
    stdout: str
    stderr: str


class AgentAdapter(Protocol):
    def start(self, workspace: Path, instruction: str) -> subprocess.Popen[str]: ...

    def collect_result(self, proc: subprocess.Popen[str], timeout_seconds: int) -> AgentRunResult: ...

    def cancel(self, proc: subprocess.Popen[str]) -> None: ...


class SubprocessAgentAdapter:
    def __init__(self, executable: str) -> None:
        self.executable = executable

    def start(self, workspace: Path, instruction: str) -> subprocess.Popen[str]:
        # Generic adapter: send instruction as CLI args so it works with wrappers/scripts.
        return subprocess.Popen(
            [self.executable, instruction],
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def collect_result(self, proc: subprocess.Popen[str], timeout_seconds: int) -> AgentRunResult:
        out, err = proc.communicate(timeout=timeout_seconds)
        return AgentRunResult(exit_code=proc.returncode or 0, stdout=out or "", stderr=err or "")

    def cancel(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is None:
            proc.terminate()


def build_agent_adapter(agent_name: str) -> AgentAdapter:
    if agent_name == "codex":
        return SubprocessAgentAdapter("codex")
    if agent_name == "claude-code":
        return SubprocessAgentAdapter("claude")
    raise ValueError(f"Unsupported agent: {agent_name}")
