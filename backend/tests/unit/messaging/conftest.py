from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _fix_web_channel():
    """Guard messaging tests from MagicMock leaks in get_message_broker.

    Some tests in other modules patch get_message_broker with a plain MagicMock
    (not AsyncMock) at module level. That breaks the ``await broker.publish(...)``
    calls in ``web_channel``.  This fixture re‑patches the reference where it
    is used (web_channel.get_message_broker) with a proper AsyncMock for every
    messaging test.
    """
    broker = AsyncMock()
    broker.publish = AsyncMock()
    with patch("app.core.channel.output.web_channel.get_message_broker", return_value=broker):
        yield

