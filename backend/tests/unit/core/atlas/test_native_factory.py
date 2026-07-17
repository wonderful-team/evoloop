"""Unit tests for the native macro generator (M3) — pure functions only."""

from app.core.atlas.source.native_factory import (
    MAX_MENU_DEPTH,
    generate_field_macros,
    generate_menu_macros,
)

BUNDLE = "com.google.Chrome"
APP = "Chrome"


def _menu_el(label, path, role="AXMenuItem", actions=None, shortcut=""):
    return {
        "role": role,
        "label": label,
        "ax_path": path,
        "parent_menu": "",
        "shortcut": shortcut,
        "metadata": {"extra": {"actions": actions if actions is not None else ["AXPress"], "region": "menubar"}},
    }


MENUBAR = [
    _menu_el("文件", "menubar > AXMenuBarItem 1", role="AXMenuBarItem"),
    _menu_el("新建标签页", "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 1", shortcut="t"),
    _menu_el("新建窗口", "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 2", shortcut="n"),
    _menu_el("书签", "menubar > AXMenuBarItem 2", role="AXMenuBarItem"),
    _menu_el("收藏此页", "menubar > AXMenuBarItem 2 > AXMenu 1 > AXMenuItem 1"),
    _menu_el("历史记录", "menubar > AXMenuBarItem 3", role="AXMenuBarItem"),
    _menu_el("清除浏览数据", "menubar > AXMenuBarItem 3 > AXMenu 1 > AXMenuItem 1"),
    _menu_el("Chrome", "menubar > AXMenuBarItem 4", role="AXMenuBarItem"),
    _menu_el("退出 Chrome", "menubar > AXMenuBarItem 4 > AXMenu 1 > AXMenuItem 9", shortcut="q"),
    _menu_el("一级", "menubar > AXMenuBarItem 4 > AXMenu 1 > AXMenuItem 1"),
    _menu_el("二级", "menubar > AXMenuBarItem 4 > AXMenu 1 > AXMenuItem 1 > AXMenu 1 > AXMenuItem 1"),
    _menu_el("深层项", "menubar > AXMenuBarItem 4 > AXMenu 1 > AXMenuItem 1 > AXMenu 1 > AXMenuItem 1 > AXMenu 1 > AXMenuItem 1"),
    _menu_el("", "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 8"),  # separator
    _menu_el("无动作项", "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 9", actions=[]),
]

WINDOW = [
    {"role": "AXTextField", "label": "地址和搜索栏", "ax_path": "window 1 > AXGroup 1 > AXTextField 1",
     "metadata": {"extra": {"actions": ["AXConfirm", "AXShowMenu"], "region": "window"}}},
    {"role": "AXSearchField", "label": "搜索", "ax_path": "window 1 > AXToolbar 1 > AXSearchField 1",
     "metadata": {"extra": {"actions": ["AXConfirm"], "region": "window"}}},
    {"role": "AXTextField", "label": "文件名", "ax_path": "window 1 > AXOutline 1 > AXRow 1 > AXTextField 1",
     "metadata": {"extra": {"actions": [], "region": "window"}}},  # 文件名单元格陷阱
    {"role": "AXTextField", "label": "", "ax_path": "window 1 > AXGroup 2 > AXTextField 1",
     "metadata": {"extra": {"actions": ["AXConfirm"], "region": "window"}}},  # 无名字段
    {"role": "AXButton", "label": "保存", "ax_path": "window 1 > AXGroup 1 > AXButton 1",
     "metadata": {"extra": {"actions": ["AXPress"], "region": "window"}}},
]


class TestMenuMacros:
    def test_basic_generation(self):
        cands = generate_menu_macros(BUNDLE, APP, MENUBAR)
        by_name = {c.name: c for c in cands}
        assert f"{APP} 文件>新建标签页" in by_name
        m = by_name[f"{APP} 文件>新建标签页"]
        assert m.steps[0]["event_type"] == "open_app"
        assert m.steps[0]["payload"] == {"bundle_id": BUNDLE, "focus": False}
        assert m.steps[1]["event_type"] == "ax_menu_press"
        assert m.steps[1]["payload"]["menu_labels"] == ["文件", "新建标签页"]
        assert m.risk_tier == "ui"
        assert not m.requires_confirmation

    def test_dynamic_roots_skipped(self):
        cands = generate_menu_macros(BUNDLE, APP, MENUBAR)
        names = [c.name for c in cands]
        assert not any("书签>" in n or "收藏此页" in n for n in names)
        assert not any("历史记录>" in n for n in names)

    def test_quit_requires_confirmation(self):
        cands = generate_menu_macros(BUNDLE, APP, MENUBAR)
        quit_c = next(c for c in cands if "退出" in c.name)
        assert quit_c.requires_confirmation

    def test_depth_capped(self):
        cands = generate_menu_macros(BUNDLE, APP, MENUBAR)
        assert not any("深层项" in c.name for c in cands)
        for c in cands:
            assert len(c.labels_chain) <= MAX_MENU_DEPTH

    def test_root_level_filtered(self):
        cands = generate_menu_macros(BUNDLE, APP, MENUBAR)
        # 链长1=按根菜单（仅弹菜单，非指令）→ 不出宏
        assert all(len(c.labels_chain) >= 2 for c in cands)
        assert not {c.name for c in cands} & {f"{APP} 文件", f"{APP} 书签", f"{APP} Chrome"}

    def test_tiling_submenus_filtered(self):
        menubar = MENUBAR + [
            _menu_el("窗口", "menubar > AXMenuBarItem 5", role="AXMenuBarItem"),
            _menu_el("最小化", "menubar > AXMenuBarItem 5 > AXMenu 1 > AXMenuItem 1", shortcut="m"),
            _menu_el("左侧与右侧", "menubar > AXMenuBarItem 5 > AXMenu 1 > AXMenuItem 2 > AXMenu 1 > AXMenuItem 1"),
            _menu_el("移动与调整大小", "menubar > AXMenuBarItem 5 > AXMenu 1 > AXMenuItem 2"),
        ]
        cands = generate_menu_macros(BUNDLE, APP, menubar)
        names = [c.name for c in cands]
        assert any("最小化" in n for n in names)  # 普通窗口命令保留
        assert not any("左侧与右侧" in n for n in names)  # 平铺子菜单内容过滤

    def test_separator_and_actionless_skipped(self):
        cands = generate_menu_macros(BUNDLE, APP, MENUBAR)
        assert not any("无动作项" in c.name for c in cands)
        assert all(c.name.strip() for c in cands)


class TestFieldMacros:
    def test_address_bar_gets_confirm_step_and_url_triggers(self):
        cands = generate_field_macros(BUNDLE, APP, WINDOW)
        addr = next(c for c in cands if "打开网址" in c.name)
        assert len(addr.steps) == 3
        assert addr.steps[1]["event_type"] == "ax_set_value"
        assert addr.steps[1]["payload"]["text"] == "{{text}}"
        assert addr.steps[2]["event_type"] == "ax_press"
        assert addr.steps[2]["payload"]["ax_action"] == "AXConfirm"
        assert "打开{{text}}" in addr.trigger_patterns
        assert addr.parameters[0]["name"] == "text"
        assert addr.parameters[0]["required"] is True

    def test_container_and_unnamed_fields_rejected(self):
        cands = generate_field_macros(BUNDLE, APP, WINDOW)
        paths = [s["payload"]["ax_path"] for c in cands for s in c.steps if s["event_type"] == "ax_set_value"]
        assert not any("AXOutline" in p for p in paths)
        assert all(p for p in paths)

    def test_plain_search_field(self):
        cands = generate_field_macros(BUNDLE, APP, WINDOW)
        search = next(c for c in cands if "搜索输入" in c.name)
        assert search.risk_tier == "data"
        assert any("{{text}}" in t for t in search.trigger_patterns)
