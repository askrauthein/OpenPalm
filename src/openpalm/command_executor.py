from __future__ import annotations

import subprocess
import time

from openpalm.models import CommandResult


class CommandExecutor:
    def __init__(
        self,
        shell: str,
        working_dir: str,
        timeout_seconds: int,
        max_output_chars: int,
    ) -> None:
        self.shell = shell
        self.working_dir = working_dir
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def execute(self, command: str) -> CommandResult:
        start = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                shell=True,
                executable=self.shell,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            stdout, stderr, truncated = self._truncate(completed.stdout, completed.stderr)
            return CommandResult(
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=completed.returncode,
                timed_out=False,
                truncated=truncated,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            stdout, stderr, truncated = self._truncate(stdout, stderr)
            return CommandResult(
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=None,
                timed_out=True,
                truncated=truncated,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

    def _truncate(self, stdout: str, stderr: str) -> tuple[str, str, bool]:
        joined = stdout + stderr
        if len(joined) <= self.max_output_chars:
            return stdout, stderr, False

        remaining = self.max_output_chars
        out_cut = stdout[:remaining]
        remaining -= len(out_cut)
        err_cut = stderr[:remaining] if remaining > 0 else ""
        return out_cut, err_cut, True
