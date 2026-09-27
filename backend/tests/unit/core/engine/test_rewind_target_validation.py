from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.core.engine.rewind.rewind import (
    MessageNotFoundError,
    _compute_affected_message_ids,
)


@pytest.mark.parametrize(
    "target",
    [None, SimpleNamespace(sequence_number=2, thread_id="other")],
)
async def test_target_outside_thread_is_rejected(monkeypatch, target):
    @asynccontextmanager
    async def _scope():
        async def _execute(_stmt):
            return SimpleNamespace(one_or_none=lambda: target)

        yield SimpleNamespace(execute=_execute)

    monkeypatch.setattr("app.core.engine.rewind.rewind.session_scope", _scope)

    with pytest.raises(MessageNotFoundError):
        await _compute_affected_message_ids(
            thread_id="current",
            target_message_id="m-target",
            include_target=True,
        )
