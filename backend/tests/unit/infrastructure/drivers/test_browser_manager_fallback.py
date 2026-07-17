"""Regression: browser_manager Mode1(CDP takeover) -> Mode2(auto-launch) fallback.

Bug: Mode 1 `connect_over_cdp` failure raises `playwright._impl._errors.Error`
(== playwright.async_api.Error), but the except only caught built-in types, so the
error propagated and Mode 2 auto-launch was unreachable dead code. Fix added
`PlaywrightError` to the except. These tests pin that Mode 1 Playwright errors are
caught and Mode 2 auto-launch is attempted (no propagation).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Error as PlaywrightError

from app.infrastructure.drivers.browser import BrowserManager


def _playwright_starter(side_effects):
    pw = MagicMock()
    pw.chromium.connect_over_cdp = AsyncMock(side_effect=side_effects)
    starter = MagicMock()
    starter.start = AsyncMock(return_value=pw)
    return starter, pw


@pytest.mark.asyncio
async def test_mode1_playwright_error_falls_through_to_mode2():
    bm = BrowserManager()
    ctx = MagicMock()
    ctx.pages = [MagicMock()]
    browser = MagicMock()
    browser.contexts = [ctx]

    starter, pw = _playwright_starter([PlaywrightError("connect ECONNREFUSED ::1:9222"), browser])

    with (
        patch("playwright.async_api.async_playwright", return_value=starter),
        patch("subprocess.Popen", return_value=MagicMock(pid=12345)),
        patch("subprocess.check_output", return_value=b"1"),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        await bm._start()  # must NOT raise

    # Mode 1 raised PlaywrightError -> caught -> Mode 2 ran (second connect_over_cdp)
    assert pw.chromium.connect_over_cdp.await_count == 2
    assert bm._context is ctx
    assert bm._is_cdp is True


@pytest.mark.asyncio
async def test_mode1_builtin_error_still_falls_through():
    # pre-existing built-in catch must keep working (connection refused as OSError)
    bm = BrowserManager()
    ctx = MagicMock()
    ctx.pages = [MagicMock()]
    browser = MagicMock()
    browser.contexts = [ctx]

    starter, pw = _playwright_starter([OSError("refused"), browser])

    with (
        patch("playwright.async_api.async_playwright", return_value=starter),
        patch("subprocess.Popen", return_value=MagicMock(pid=12345)),
        patch("subprocess.check_output", return_value=b"1"),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        await bm._start()

    assert pw.chromium.connect_over_cdp.await_count == 2
    assert bm._context is ctx
