"""Tests for research tool timeout fallback (no Traceback on expected timeout)."""

import asyncio
from unittest.mock import patch

import pytest

from app.domain.tools.research import _search_parallel


@pytest.mark.asyncio
async def test_search_parallel_timeout_returns_none_without_crash():
    """Web search 8s hard timeout → returns None (graceful degradation), no exception."""
    async def _slow(_query):
        await asyncio.sleep(30)
        return ["slow result"]

    with patch(
        "app.domain.tools.research._search_parallel_inner",
        new=_slow,
    ), patch(
        "app.domain.tools.research.logger",
    ) as mock_logger:
        result = await _search_parallel("test query")
    assert result is None
    # 超时是预期降级：不应打印 exc_info（无 Traceback）
    mock_logger.debug.assert_called_once()
    call = mock_logger.debug.call_args
    assert "exc_info" not in call.kwargs
