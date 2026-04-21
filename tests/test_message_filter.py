from datetime import datetime, timedelta, timezone

from openpalm.message_filter import MessageFilter
from openpalm.models import IncomingMessage


def _msg(**kwargs):
    base = dict(
        message_id="1",
        from_jid="me@wa",
        to_jid="me@wa",
        text="pwd",
        timestamp=datetime.now(timezone.utc),
        message_type="text",
        from_me=True,
    )
    base.update(kwargs)
    return IncomingMessage(**base)


def test_accepts_valid_self_text_message():
    f = MessageFilter(own_jid="me@wa")
    assert f.is_valid_text_from_self_to_self(_msg()) is True


def test_rejects_non_text_messages():
    f = MessageFilter(own_jid="me@wa")
    assert f.is_valid_text_from_self_to_self(_msg(message_type="image")) is False


def test_rejects_old_messages():
    f = MessageFilter(own_jid="me@wa", max_age_minutes=1)
    old = datetime.now(timezone.utc) - timedelta(minutes=3)
    assert f.is_valid_text_from_self_to_self(_msg(timestamp=old)) is False
