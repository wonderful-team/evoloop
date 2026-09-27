"""Unit tests for ActivityMonitor.set_human_request validation + publishing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.monitoring.activity import ActivityMonitor, system_bus
from app.core.monitoring.schemas import HumanRequestData


def _make_monitor():
    monitor = ActivityMonitor.__new__(ActivityMonitor)
    state = AsyncMock()
    state.set_human_request = AsyncMock(return_value=True)
    monitor._state_service = state
    return monitor, state


@pytest.mark.asyncio
async def test_set_human_request_unknown_type_logs_warning():
    monitor, state = _make_monitor()
    with (
        patch.object(monitor, "_state_service", state),
        patch.object(system_bus, "publish", AsyncMock()),
        patch("app.core.monitoring.activity.logger") as logger,
    ):
        await monitor.set_human_request(
            "t-1",
            HumanRequestData(type="bogus_type", prompt="hi"),
        )
    state.set_human_request.assert_awaited_once()
    logger.warning.assert_called_once()
    assert "Unknown request type" in logger.warning.call_args[0][0]


@pytest.mark.asyncio
async def test_set_human_request_valid_type_no_warning():
    monitor, state = _make_monitor()
    with (
        patch.object(monitor, "_state_service", state),
        patch.object(system_bus, "publish", AsyncMock()),
        patch("app.core.monitoring.activity.logger") as logger,
    ):
        await monitor.set_human_request(
            "t-1",
            HumanRequestData(type="approval", prompt="deploy?"),
        )
    state.set_human_request.assert_awaited_once()
    logger.warning.assert_not_called()
