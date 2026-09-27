"""Unit tests for the desktop shortcuts lookup table.

Covers `get_shortcut` lookup precedence (app-specific → generic → system),
input normalization, and data sanity guarantees.
"""

from __future__ import annotations

import pytest

from app.core.environment.controllers.desktop.shortcuts import (
    GENERIC_SHORTCUTS,
    SHORTCUTS,
    SYSTEM_SHORTCUTS,
    get_shortcut,
)


@pytest.mark.unit
class TestGetShortcut:
    def test_app_specific_chinese_label(self) -> None:
        assert get_shortcut("com.tencent.xinWeChat", "发送") == "return"

    def test_app_specific_english_key(self) -> None:
        assert get_shortcut("com.tencent.xinWeChat", "close") == "cmd+w"

    def test_app_specific_snake_case_normalization(self) -> None:
        assert get_shortcut("com.google.Chrome", "Address Bar") == "cmd+l"

    def test_generic_fallback_for_unknown_app(self) -> None:
        assert get_shortcut("com.unknown.app", "复制") == "cmd+c"

    def test_generic_snake_case_fallback(self) -> None:
        assert get_shortcut("", "select_all") == "cmd+a"

    def test_system_shortcut_with_unknown_app(self) -> None:
        assert get_shortcut("", "切换应用") == "cmd+tab"

    def test_system_shortcut_english_key(self) -> None:
        assert get_shortcut("com.unknown.app", "Spotlight") == "cmd+space"

    def test_app_specific_precedence_over_generic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(SHORTCUTS, "com.example.app", {"复制": "cmd+shift+c"})
        try:
            assert get_shortcut("com.example.app", "复制") == "cmd+shift+c"
        finally:
            monkeypatch.delitem(SHORTCUTS, "com.example.app")

    def test_unknown_element_returns_none(self) -> None:
        assert get_shortcut("com.tencent.xinWeChat", "不存在的元素") is None

    def test_unknown_app_and_element_returns_none(self) -> None:
        assert get_shortcut("", "") is None


@pytest.mark.unit
class TestShortcutData:
    """Data sanity: no empty values (the walrus lookup depends on truthiness)."""

    def test_tables_are_not_empty(self) -> None:
        assert SHORTCUTS
        assert GENERIC_SHORTCUTS
        assert SYSTEM_SHORTCUTS

    def test_no_empty_shortcut_values(self) -> None:
        for app_mapping in SHORTCUTS.values():
            for shortcut in app_mapping.values():
                assert shortcut.strip(), f"empty shortcut value in {app_mapping}"
        for shortcut in GENERIC_SHORTCUTS.values():
            assert shortcut.strip(), "empty shortcut value in GENERIC_SHORTCUTS"
        for shortcut in SYSTEM_SHORTCUTS.values():
            assert shortcut.strip(), "empty shortcut value in SYSTEM_SHORTCUTS"
