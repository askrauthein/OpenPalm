from pathlib import Path

from openpalm.command_state import CommandStateManager
from openpalm.storage import JsonStorage


def test_default_state_is_disabled(tmp_path: Path):
    state = CommandStateManager(JsonStorage(tmp_path / "state.json")).load()
    assert state.command_interpreter_enabled is False


def test_can_persist_enabled_state(tmp_path: Path):
    manager = CommandStateManager(JsonStorage(tmp_path / "state.json"))
    manager.set_enabled(True)

    state = manager.load()
    assert state.command_interpreter_enabled is True
