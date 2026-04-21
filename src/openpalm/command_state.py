from __future__ import annotations

from dataclasses import dataclass

from openpalm.storage import JsonStorage


@dataclass(slots=True)
class CommandState:
    command_interpreter_enabled: bool = False


class CommandStateManager:
    def __init__(self, state_file_storage: JsonStorage) -> None:
        self.storage = state_file_storage

    def load(self) -> CommandState:
        raw = self.storage.read(default={"command_interpreter_enabled": False})
        return CommandState(command_interpreter_enabled=bool(raw.get("command_interpreter_enabled", False)))

    def set_enabled(self, enabled: bool) -> CommandState:
        state = CommandState(command_interpreter_enabled=enabled)
        self.storage.write({"command_interpreter_enabled": state.command_interpreter_enabled})
        return state
