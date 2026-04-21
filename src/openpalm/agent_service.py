from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from openpalm.agent.adapters import build_agent_adapter
from openpalm.agent_config import AgentPaths, load_agent_paths
from openpalm.agent_models import AgentRuntimeState, Job, Project
from openpalm.agent_state import AgentStateStore
from openpalm.git_ops import GitOps
from openpalm.job_store import JobStore
from openpalm.oneoff_runner import OneOffRunner
from openpalm.project_registry import ProjectRegistry


@dataclass(slots=True)
class AgentCommandResult:
    handled: bool
    reply: str | None = None


class AgentService:
    def __init__(self, notify: callable | None = None) -> None:
        self.paths: AgentPaths = load_agent_paths()
        self.projects = ProjectRegistry(self.paths.projects_file)
        self.state_store = AgentStateStore(self.paths.state_file)
        self.state = self.state_store.load()
        self.jobs = JobStore(self.paths.jobs_db)
        self.git = GitOps()
        self.oneoff = OneOffRunner(Path.home())
        self.notify = notify

        self._queue: Queue[str] = Queue()
        self._active_projects: set[str] = set()
        self._active_procs: dict[str, object] = {}
        self._active_oneoff: dict[str, dict[str, str]] = {}
        self._runtime_lock = threading.Lock()
        self._oneoff_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="openpalm-oneoff")
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def handle_text(self, text: str) -> AgentCommandResult:
        t = text.strip()
        if not t.startswith("/"):
            return AgentCommandResult(False)
        if t == "/status":
            return AgentCommandResult(True, self._status_overview())

        if t.startswith("/project "):
            return AgentCommandResult(True, self._handle_project_cmd(t))
        if t.startswith("/agent "):
            return AgentCommandResult(True, self._handle_agent_cmd(t))
        if t.startswith("/task "):
            return AgentCommandResult(True, self._handle_task_cmd(t))
        if t.startswith("/job "):
            return AgentCommandResult(True, self._handle_job_cmd(t))
        if t == "/ask" or t.startswith("/ask "):
            return AgentCommandResult(True, self._handle_ask_cmd(t))
        if t == "/tokens":
            return AgentCommandResult(True, self._handle_tokens_cmd())

        return AgentCommandResult(False)

    def _status_overview(self) -> str:
        active = self.jobs.list_active_jobs(limit=100)
        with self._runtime_lock:
            active_oneoff = dict(self._active_oneoff)
        if not active and not active_oneoff:
            return "No active requests are currently running."

        lines = ["Active requests:"]
        for req_id, info in sorted(active_oneoff.items()):
            lines.append(
                f"- {req_id} [running] type=ask agent={info.get('agent','?')} started={info.get('started_at','?')}"
            )
        for j in active:
            lines.append(
                f"- {j.job_id} [{j.status}] project={j.project_id} agent={j.agent} updated={j.updated_at.isoformat()}"
            )
        return "\n".join(lines)

    def _handle_project_cmd(self, t: str) -> str:
        parts = t.split()
        if len(parts) < 2:
            return "Usage: /project <action> ..."
        action = parts[1]

        if action == "add-local" and len(parts) >= 4:
            project_id, path = parts[2], " ".join(parts[3:])
            p = Project(
                project_id=project_id,
                source_type="local",
                path=path,
                repo=None,
                clone_url=None,
                git_remote=None,
                default_branch="main",
                cache_path=None,
                marker_file=".project-agent.toml",
                allowed_agents=["codex", "claude-code"],
                enabled=True,
            )
            self.projects.add(p)
            return f"Project added: {project_id} (local)"

        if action == "add-github" and len(parts) >= 4:
            project_id, clone_url = parts[2], parts[3]
            cache_path = str(self.paths.repos_dir / project_id)
            p = Project(
                project_id=project_id,
                source_type="github",
                path=None,
                repo=_repo_from_clone_url(clone_url),
                clone_url=clone_url,
                git_remote=clone_url,
                default_branch="main",
                cache_path=cache_path,
                marker_file=".project-agent.toml",
                allowed_agents=["codex", "claude-code"],
                enabled=True,
            )
            self.projects.add(p)
            return f"Project added: {project_id} (github)"

        if action == "list":
            items = self.projects.list_projects()
            if not items:
                return "No projects registered."
            return "\n".join([f"- {p.project_id} [{p.source_type}]" for p in items])

        if action == "info" and len(parts) >= 3:
            p = self.projects.get(parts[2])
            if not p:
                return "Project not found."
            return json.dumps(p.__dict__, indent=2)

        if action == "use" and len(parts) >= 3:
            pid = parts[2]
            if not self.projects.get(pid):
                return "Project not found."
            self.state.current_project = pid
            self.state_store.save(self.state)
            return f"Current project set to: {pid}"

        if action == "current":
            return f"Current project: {self.state.current_project or '(none)'}"

        if action == "remove" and len(parts) >= 3:
            pid = parts[2]
            self.projects.remove(pid)
            if self.state.current_project == pid:
                self.state.current_project = None
                self.state_store.save(self.state)
            return f"Project removed: {pid}"

        if action in {"checkout", "update"} and len(parts) >= 3:
            pid = parts[2]
            ref = _read_kv(parts[3:], "branch") or _read_kv(parts[3:], "tag") or _read_kv(parts[3:], "commit")
            p = self.projects.get(pid)
            if not p:
                return "Project not found."
            repo_path = self.git.update_cache(p)
            base_ref = ref or p.default_branch
            self.git.validate_project(p, repo_path, base_ref)
            return f"Project ready: {pid}\nPath: {repo_path}\nRef: {base_ref}"

        return "Unsupported /project command."

    def _handle_agent_cmd(self, t: str) -> str:
        parts = t.split()
        if len(parts) < 2:
            return "Usage: /agent <action>"
        action = parts[1]

        if action == "enable":
            self.state.agent_mode_enabled = True
            self.state_store.save(self.state)
            return "Agent mode enabled."
        if action == "disable":
            self.state.agent_mode_enabled = False
            self.state_store.save(self.state)
            return "Agent mode disabled."
        if action == "use" and len(parts) >= 3:
            agent = parts[2]
            if agent not in {"codex", "claude-code"}:
                return "Unsupported agent. Use codex or claude-code."
            self.state.current_agent = agent
            self.state_store.save(self.state)
            return f"Current agent set to: {agent}"
        if action == "current":
            return f"Current agent: {self.state.current_agent}"

        return "Unsupported /agent command."

    def _handle_task_cmd(self, t: str) -> str:
        if not self.state.agent_mode_enabled:
            return "Agent mode is disabled. Use /agent enable first."

        payload = t[len("/task ") :].strip()
        kv, instruction = _extract_kv_prefix(payload)

        project_id = kv.get("project") or self.state.current_project
        if not project_id:
            return "Job rejected. No project specified and no current project set."

        project = self.projects.get(project_id)
        if not project:
            return f"Job rejected. Unknown project: {project_id}"

        agent = kv.get("agent") or self.state.current_agent
        if agent not in {"codex", "claude-code"}:
            return "Job rejected. Unsupported agent."
        if project.allowed_agents and agent not in project.allowed_agents:
            return f"Job rejected. Agent {agent} is not allowed for project {project_id}."

        if not instruction:
            return "Job rejected. Missing instruction text."

        base_ref = kv.get("ref") or project.default_branch

        job_id = self._next_job_id()
        work_branch = f"task/{job_id.replace('job-', '')}-{_slug(instruction)}"
        workspace_path = str(self.paths.jobs_dir / f"{job_id}-{project_id}")
        now = datetime.now(timezone.utc)
        job = Job(
            job_id=job_id,
            project_id=project_id,
            agent=agent,
            instruction=instruction,
            base_ref=base_ref,
            workspace_path=workspace_path,
            work_branch=work_branch,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self.jobs.create_job(job)
        self.jobs.add_event(job_id, "job_created", instruction)
        self._queue.put(job_id)
        return (
            f"Job {job_id} created.\n"
            f"Project: {project_id}\n"
            f"Agent: {agent}\n"
            f"Base ref: {base_ref}\n"
            "Status: queued"
        )

    def _handle_job_cmd(self, t: str) -> str:
        parts = t.split()
        if len(parts) < 2:
            return "Usage: /job <list|status|result|logs|cancel> ..."
        action = parts[1]

        if action == "list":
            jobs = self.jobs.list_jobs()
            if not jobs:
                return "No jobs found."
            return "\n".join([f"- {j.job_id} [{j.status}] project={j.project_id} agent={j.agent}" for j in jobs])

        if action in {"status", "result", "logs", "cancel"} and len(parts) >= 3:
            job_id = parts[2]
            job = self.jobs.get(job_id)
            if not job:
                return "Job not found."

            if action == "status":
                return f"{job.job_id}: {job.status}"
            if action == "result":
                return (
                    f"{job.job_id} result\n"
                    f"status: {job.status}\n"
                    f"summary: {job.result_summary or '(none)'}\n"
                    f"error: {job.error_message or '(none)'}"
                )
            if action == "logs":
                events = self.jobs.list_events(job_id, limit=30)
                if not events:
                    return "No logs for this job."
                lines = [f"{e['ts']} {e['event_type']} {e['payload']}" for e in reversed(events)]
                return "\n".join(lines)
            if action == "cancel":
                self.jobs.cancel(job_id)
                self.jobs.add_event(job_id, "job_cancelled", "requested by user")
                with self._runtime_lock:
                    proc = self._active_procs.get(job_id)
                if proc is not None:
                    try:
                        proc.terminate()
                    except Exception:  # noqa: BLE001
                        pass
                return f"Job cancelled: {job_id}"

        return "Unsupported /job command."

    def _handle_ask_cmd(self, t: str) -> str:
        payload = t[len("/ask") :].strip()
        kv, prompt = _extract_kv_prefix(payload)
        agent = kv.get("agent") or self.state.current_agent
        if agent not in {"codex", "claude-code"}:
            return "Unsupported agent. Use codex or claude-code."
        if not prompt:
            return "Usage: /ask [agent=codex|claude-code] <prompt>"

        request_id = self._next_request_id()
        started = datetime.now(timezone.utc).isoformat()
        with self._runtime_lock:
            self._active_oneoff[request_id] = {"agent": agent, "started_at": started}
        self._oneoff_pool.submit(self._run_oneoff_request, request_id, agent, prompt)
        return (
            f"Request {request_id} started.\n"
            f"Type: ask\n"
            f"Agent: {agent}\n"
            "Status: running"
        )

    def _handle_tokens_cmd(self) -> str:
        totals = self.jobs.token_totals()
        codex_total = totals.get("codex", 0)
        claude_total = totals.get("claude-code", 0)
        return (
            "Token totals (one-off runs)\n"
            f"- codex: {codex_total}\n"
            f"- claude-code: {claude_total}"
        )

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._run_job(job_id)
            except Exception as exc:  # noqa: BLE001
                self.jobs.update_status(job_id, "failed", error=str(exc))
                self.jobs.add_event(job_id, "job_failed", str(exc))
                self._notify(f"Job {job_id} failed.\nReason: {exc}")

    def _run_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return

        if self.jobs.is_cancelled(job_id):
            return

        project = self.projects.get(job.project_id)
        if not project:
            raise ValueError(f"Project not found: {job.project_id}")
        with self._runtime_lock:
            if (not self.state.allow_parallel_jobs) and project.project_id in self._active_projects:
                self._queue.put(job_id)
                return
            self._active_projects.add(project.project_id)

        try:
            self.jobs.update_status(job_id, "preparing_project")
            self._notify(f"Job {job_id} started. Preparing project {job.project_id}.")

            repo_path = self.git.ensure_materialized(project)

            self.jobs.update_status(job_id, "validating_project")
            self.git.validate_project(project, repo_path, job.base_ref)
            self.jobs.add_event(job_id, "project_validated", str(repo_path))
            self._notify(f"Job {job_id}. Project validated successfully. Repo: {job.project_id}")

            self.jobs.update_status(job_id, "creating_workspace")
            workspace = Path(job.workspace_path)
            self.git.create_workspace(project, repo_path, workspace, job.base_ref, job.work_branch)
            self.jobs.add_event(job_id, "workspace_created", str(workspace))

            if self.jobs.is_cancelled(job_id):
                self.jobs.update_status(job_id, "cancelled")
                return

            self.jobs.update_status(job_id, "starting_agent")
            adapter = build_agent_adapter(job.agent)
            self._notify(f"Job {job_id} in progress. Stage: starting {job.agent}.")

            proc = adapter.start(workspace, job.instruction)
            with self._runtime_lock:
                self._active_procs[job_id] = proc
            self.jobs.update_status(job_id, "running")
            self.jobs.add_event(job_id, "agent_started", job.agent)

            try:
                result = adapter.collect_result(proc, timeout_seconds=30 * 60)
            except Exception as exc:  # noqa: BLE001
                adapter.cancel(proc)
                raise RuntimeError(f"Agent execution failed: {exc}") from exc

            self.jobs.update_status(job_id, "collecting_results")
            summary = _build_summary(result.stdout, result.stderr, result.exit_code)

            if result.exit_code == 0:
                self.jobs.update_status(job_id, "succeeded", summary=summary)
                self.jobs.add_event(job_id, "job_finished", "success")
                self._notify(f"Job {job_id} completed.\nSummary: {summary}")
            else:
                self.jobs.update_status(job_id, "failed", summary=summary, error=result.stderr[:500])
                self.jobs.add_event(job_id, "job_finished", "failed")
                self._notify(f"Job {job_id} failed.\nSummary: {summary}")
        finally:
            with self._runtime_lock:
                self._active_projects.discard(project.project_id)
                self._active_procs.pop(job_id, None)

    def _notify(self, text: str) -> None:
        if self.notify:
            self.notify(text)

    def _next_job_id(self) -> str:
        now = datetime.now(timezone.utc)
        return f"job-{int(now.timestamp())}"

    def _next_request_id(self) -> str:
        now = datetime.now(timezone.utc)
        return f"ask-{int(now.timestamp() * 1000)}"

    def _run_oneoff_request(self, request_id: str, agent: str, prompt: str) -> None:
        try:
            result = self.oneoff.run(agent=agent, prompt=prompt)
            self.jobs.record_oneoff_run(
                agent=agent,
                prompt=prompt,
                answer=result.answer,
                raw_output=result.raw_output,
                tokens_used=result.tokens_used,
                exit_code=result.exit_code,
                error=result.error,
            )
            lines = [f"Request {request_id} finished.", f"Agent: {agent}", "", result.answer.strip() or "(no parsed answer)"]
            if result.tokens_used is not None:
                lines.append("")
                lines.append(f"tokens used: {result.tokens_used}")
            if result.exit_code != 0:
                lines.append("")
                lines.append(f"exit code: {result.exit_code}")
                if result.error:
                    lines.append(result.error[:500])
            self._notify("\n".join(lines).strip())
        except Exception as exc:  # noqa: BLE001
            self._notify(f"Request {request_id} failed.\nAgent: {agent}\nReason: {exc}")
        finally:
            with self._runtime_lock:
                self._active_oneoff.pop(request_id, None)


def _extract_kv_prefix(payload: str) -> tuple[dict[str, str], str]:
    kv: dict[str, str] = {}
    rest = payload
    while True:
        m = re.match(r"^([a-zA-Z_]+)=([^\s]+)\s*(.*)$", rest)
        if not m:
            break
        kv[m.group(1).lower()] = m.group(2)
        rest = m.group(3)
    return kv, rest.strip()


def _read_kv(parts: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for p in parts:
        if p.startswith(prefix):
            return p[len(prefix) :]
    return None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:48] or "task"


def _repo_from_clone_url(url: str) -> str | None:
    m = re.search(r"[:/]([^/:]+/[^/.]+)(?:\.git)?$", url)
    return m.group(1) if m else None


def _build_summary(stdout: str, stderr: str, exit_code: int) -> str:
    if exit_code == 0:
        snippet = (stdout or "").strip().splitlines()
        if snippet:
            return snippet[-1][:280]
        return "Agent completed successfully"
    err = (stderr or "").strip().splitlines()
    return (err[-1] if err else f"Agent exited with code {exit_code}")[:280]
