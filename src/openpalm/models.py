from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class GlobalState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    AWAITING_QR_SCAN = "AWAITING_QR_SCAN"
    CONNECTED = "CONNECTED"
    LISTENING = "LISTENING"


@dataclass(slots=True)
class IncomingMessage:
    message_id: str
    from_jid: str
    to_jid: str
    text: str | None
    timestamp: datetime
    message_type: str = "text"
    from_me: bool = True


@dataclass(slots=True)
class CommandResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool
    truncated: bool
    duration_ms: int
