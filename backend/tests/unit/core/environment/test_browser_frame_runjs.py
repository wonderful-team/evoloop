"""Unit tests for BrowserController run_js with frame_selector / frame_wait_for_selector."""


import pytest

from app.core.environment.controllers.browser.advanced import BrowserAdvancedMixin


class _FakeFrame:
    def __init__(self, url, item_present):
        self.url = url
        self._item_present = item_present
        self.evaluate_calls = []

    async def evaluate(self, script):
        self.evaluate_calls.append(script)
        if "document.querySelector" in script and not self._item_present:
            return False
        if "document.querySelector" in script and self._item_present:
            return True
        return "frame-js-ran"


class _FakePage:
    def __init__(self, frames):
        self.frames = frames

    async def evaluate(self, script):
        return "page-js-ran"


def _ctx(page, script=None, timeout_ms=15000, **kwargs):
    return {
        "page": page,
        "recording_func": None,
        "pre_url": "",
        "pre_title": "",
        "url": None,
        "tab_index": None,
        "selector": None,
        "text": None,
        "value": None,
        "key": None,
        "source_selector": None,
        "target_selector": None,
        "direction": None,
        "amount": 300,
        "clear_first": True,
        "full_page": False,
        "ocr": False,
        "attribute": None,
        "state": "visible",
        "url_pattern": None,
        "timeout_ms": timeout_ms,
        "cookies": None,
        "storage_action": None,
        "storage_key": None,
        "dialog_action": None,
        "dialog_text": None,
        "script": script or "() => 'hi'",
        "x": None,
        "y": None,
        "actions": None,
        "continue_on_error": True,
        "delay_ms": 100,
        "file_path": None,
        "kwargs": kwargs,
    }


@pytest.mark.asyncio
async def test_run_js_frame_selector_matches_by_url():
    album = _FakeFrame("http://x/shop/album/album.html", item_present=True)
    page = _FakePage([_FakeFrame("http://x/shop.html", item_present=False), album])

    res = await BrowserAdvancedMixin._handle_advanced(
        action="run_js",
        **_ctx(page, frame_selector="album", frame_wait_for_selector=".media-list-item"),
    )
    assert res == "JS result: frame-js-ran"
    assert album.evaluate_calls  # evaluate ran in the matched frame


@pytest.mark.asyncio
async def test_run_js_frame_selector_no_match_returns_error():
    page = _FakePage([_FakeFrame("http://x/shop.html", item_present=False)])

    res = await BrowserAdvancedMixin._handle_advanced(
        action="run_js",
        **_ctx(page, timeout_ms=500, frame_selector="album", frame_wait_for_selector=".media-list-item"),
    )
    assert "No iframe matched" in str(res)


@pytest.mark.asyncio
async def test_run_js_frame_wait_detects_item_in_blank_url_frame():
    # iframe src is empty ('') but the inner document contains the target item
    album = _FakeFrame("", item_present=True)
    page = _FakePage([_FakeFrame("http://x/shop.html", item_present=False), album])

    res = await BrowserAdvancedMixin._handle_advanced(
        action="run_js",
        **_ctx(page, frame_selector="album", frame_wait_for_selector=".media-list-item"),
    )
    assert res == "JS result: frame-js-ran"


@pytest.mark.asyncio
async def test_run_js_without_frame_selector_runs_on_page():
    page = _FakePage([_FakeFrame("http://x/other", item_present=False)])

    res = await BrowserAdvancedMixin._handle_advanced(
        action="run_js", **_ctx(page)
    )
    assert res == "JS result: page-js-ran"
