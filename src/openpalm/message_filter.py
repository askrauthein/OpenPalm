from __future__ import annotations

from datetime import datetime, timedelta, timezone

from openpalm.models import IncomingMessage


class MessageFilter:
    def __init__(self, own_jid: str, max_age_minutes: int = 5) -> None:
        self.own_jid = own_jid
        self.max_age_minutes = max_age_minutes

    def is_valid_text_from_self_to_self(self, msg: IncomingMessage) -> bool:
        return self.validation_reason(msg) is None

    def validation_reason(self, msg: IncomingMessage) -> str | None:
        if msg.message_type != "text":
            return "non_text"
        if not msg.text:
            return "empty_text"
        if not msg.from_me:
            return "not_from_me"
        if msg.to_jid.endswith("@g.us"):
            return "group_chat"

        # In some protocol variants (LID), self-chat may arrive with
        # from_jid == to_jid and an @lid suffix.
        if msg.from_me and msg.from_jid == msg.to_jid:
            return None

        own_user = _jid_user(self.own_jid)
        to_user = _jid_user(msg.to_jid)
        if not own_user or to_user != own_user:
            return f"destination_is_not_self (own={self.own_jid}, to={msg.to_jid})"

        now = datetime.now(timezone.utc)
        msg_ts = msg.timestamp.astimezone(timezone.utc)
        if msg_ts < now - timedelta(minutes=self.max_age_minutes):
            return "stale_message"

        return None


def _jid_user(jid: str) -> str:
    return jid.split("@", 1)[0].strip()
