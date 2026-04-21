from __future__ import annotations

from openpalm.agent_service import AgentService


def test_task_requires_project(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPALM_AGENT_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("OPENPALM_AGENT_CACHE_DIR", str(tmp_path / "cache"))

    service = AgentService()
    r = service.handle_text("/task agent=codex fix login")
    assert r.handled is True
    assert "No project specified" in (r.reply or "")


def test_add_local_and_use_project(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPALM_AGENT_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("OPENPALM_AGENT_CACHE_DIR", str(tmp_path / "cache"))

    repo = tmp_path / "repo"
    repo.mkdir(parents=True)

    service = AgentService()
    service.handle_text(f"/project add-local api {repo}")
    service.handle_text("/project use api")
    current = service.handle_text("/project current")
    assert current.reply == "Current project: api"


def test_agent_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENPALM_AGENT_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("OPENPALM_AGENT_CACHE_DIR", str(tmp_path / "cache"))

    service = AgentService()
    service.handle_text("/agent use claude-code")
    r = service.handle_text("/agent current")
    assert r.reply == "Current agent: claude-code"
