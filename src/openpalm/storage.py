from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


class JsonStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self, default: dict) -> dict:
        if not self.path.exists():
            return default
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ProcessedMessageStore:
    def __init__(self, path: Path, retention_hours: int = 24) -> None:
        self.path = path
        self.retention_hours = retention_hours

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def purge_old(self) -> None:
        data = self._load()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        cleaned = {
            msg_id: ts
            for msg_id, ts in data.items()
            if _parse_iso(ts) is not None and _parse_iso(ts) >= cutoff
        }
        self._save(cleaned)

    def has(self, message_id: str) -> bool:
        self.purge_old()
        return message_id in self._load()

    def add(self, message_id: str, when: datetime) -> None:
        data = self._load()
        data[message_id] = when.astimezone(timezone.utc).isoformat()
        self._save(data)


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
