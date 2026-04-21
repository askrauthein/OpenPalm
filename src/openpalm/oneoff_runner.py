from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


@dataclass(slots=True)
class OneOffResult:
    agent: str
    prompt: str
    answer: str
    tokens_used: int | None
    raw_output: str
    exit_code: int
    error: str


class OneOffRunner:
    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    def run(self, agent: str, prompt: str) -> OneOffResult:
        cmd = self._build_command(agent, prompt)
        cp = subprocess.run(cmd, cwd=str(self.working_dir), capture_output=True, text=True)
        raw = (cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")

        answer = _extract_answer(raw, agent)
        tokens = _extract_tokens(raw)

        return OneOffResult(
            agent=agent,
            prompt=prompt,
            answer=answer,
            tokens_used=tokens,
            raw_output=raw,
            exit_code=cp.returncode,
            error=(cp.stderr or "").strip(),
        )

    def _build_command(self, agent: str, prompt: str) -> list[str]:
        if agent == "codex":
            return ["codex", "exec", "--skip-git-repo-check", prompt]
        if agent == "claude-code":
            return ["claude", "-p", prompt]
        raise ValueError(f"Unsupported one-off agent: {agent}")


def _extract_answer(raw: str, agent: str) -> str:
    lines = raw.splitlines()
    markers = ["codex", "codex:"] if agent == "codex" else ["claude", "claude-code", "claude:"]

    start = 0
    for i, line in enumerate(lines):
        if line.strip().lower() in markers:
            start = i + 1
            break

    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].strip().lower() == "tokens used":
            end = i
            break

    body = "\n".join(lines[start:end]).strip()
    if not body:
        body = raw.strip()
    return body[:7000]


def _extract_tokens(raw: str) -> int | None:
    m = re.search(r"tokens\s+used\s*\n\s*([\d,]+)", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))
