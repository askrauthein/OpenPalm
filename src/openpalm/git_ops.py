from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from openpalm.agent_models import Project


class GitOps:
    def ensure_materialized(self, project: Project) -> Path:
        if not project.path:
            raise ValueError(f"Project {project.project_id} has no path")
        
        target_path = Path(project.path).expanduser()

        if project.source_type == "local":
            return target_path

        if project.source_type == "github":
            if not project.clone_url:
                raise ValueError(f"GitHub project {project.project_id} is missing clone_url")
            
            if not (target_path / ".git").exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                self._run(["git", "clone", project.clone_url, str(target_path)], cwd=target_path.parent)
            else:
                self._run(["git", "fetch", "--all", "--prune"], cwd=target_path)
            return target_path
        
        return target_path

    def validate_project(self, project: Project, repo_path: Path, ref: str) -> None:
        if not repo_path.exists():
            raise ValueError("Project path does not exist")

        self._run(["git", "rev-parse", "--show-toplevel"], cwd=repo_path)
        top = self._run(["git", "rev-parse", "--show-toplevel"], cwd=repo_path).strip()
        if Path(top).resolve() != repo_path.resolve():
            raise ValueError("Git top-level path mismatch")

        if project.git_remote or project.clone_url:
            found = self._run(["git", "remote", "get-url", "origin"], cwd=repo_path).strip()
            expected = project.git_remote or project.clone_url
            if expected:
                def _norm(u: str) -> str:
                    u = u.strip()
                    if u.endswith(".git"):
                        u = u[:-4]
                    if u.startswith("https://github.com/"):
                        u = u[19:]
                    elif u.startswith("git@github.com:"):
                        u = u[15:]
                    elif u.startswith("ssh://git@github.com/"):
                        u = u[21:]
                    return u
                
                if _norm(found) != _norm(expected):
                    raise ValueError(f"Remote mismatch: expected {expected}, found {found}")

        if project.marker_file:
            marker = repo_path / project.marker_file
            if marker.exists():
                content = marker.read_text(encoding="utf-8", errors="ignore")
                if f'project_id = "{project.project_id}"' not in content:
                    raise ValueError("Marker project_id mismatch")

        self._resolve_ref(repo_path, ref)

    def prepare_branch(self, repo_path: Path, base_ref: str, work_branch: str) -> None:
        # Check out base ref and create new branch in the visible repo
        self._run(["git", "checkout", base_ref], cwd=repo_path)
        self._run(["git", "checkout", "-b", work_branch], cwd=repo_path)

    def update_cache(self, project: Project) -> Path:
        repo_path = self.ensure_materialized(project)
        if project.source_type == "github":
            self._run(["git", "fetch", "--all", "--prune"], cwd=repo_path)
        return repo_path

    def _resolve_ref(self, repo_path: Path, ref: str) -> None:
        self._run(["git", "rev-parse", "--verify", ref], cwd=repo_path)

    def _run(self, cmd: list[str], cwd: Path) -> str:
        cp = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        if cp.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{cp.stderr.strip()}")
        return cp.stdout
