"""Unit tests for the Atlas Native Surveyor (M2).

All AX access is mocked: dump_fn/press_fn are injected into survey_app, and
module-level functions are monkeypatched for needs_resurvey.
"""

from __future__ import annotations

import pytest

from app.core.atlas import surveyor
from app.core.atlas.surveyor import (
    MENUBAR_STATE_ID,
    AtlasSurveyor,
    SurveyPolicy,
    build_menu_tree,
    build_menubar_state,
    coverage_tier,
    element_signature,
    is_blacklisted,
    jaccard,
    menu_reachable_pct,
    signature_state_id,
)

BUNDLE = "com.example.testapp"


def _win_elements() -> list[dict]:
    return [
        {"role": "AXWindow", "name": "主窗口", "path": "window 1", "bounds": [0, 0, 800, 600],
         "actions": [], "enabled": True, "shortcut": ""},
        {"role": "AXButton", "name": "保存", "path": "window 1 > AXButton 1", "bounds": [10, 10, 60, 30],
         "actions": ["AXPress"], "enabled": True, "shortcut": ""},
        {"role": "AXRow", "name": "通用", "path": "window 1 > AXOutline 1 > AXRow 1",
         "bounds": [0, 40, 200, 24], "actions": ["AXPress"], "enabled": True, "shortcut": ""},
        {"role": "AXRow", "name": "删除所有内容", "path": "window 1 > AXOutline 1 > AXRow 2",
         "bounds": [0, 64, 200, 24], "actions": ["AXPress"], "enabled": True, "shortcut": ""},
    ]


def _menubar_elements() -> list[dict]:
    return [
        {"role": "AXMenuBarItem", "name": "文件", "path": "menubar > AXMenuBarItem 1",
         "bounds": [0, 0, 40, 20], "actions": ["AXPress"], "enabled": True, "shortcut": ""},
        {"role": "AXMenuItem", "name": "新建", "path": "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 1",
         "bounds": [0, 0, 100, 20], "actions": ["AXPress"], "enabled": True, "shortcut": "n"},
        {"role": "AXMenuItem", "name": "退出", "path": "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 2",
         "bounds": [0, 0, 100, 20], "actions": ["AXPress"], "enabled": True, "shortcut": "q"},
        {"role": "AXMenuItem", "name": "", "path": "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 3",
         "bounds": [0, 0, 100, 4], "actions": [], "enabled": False, "shortcut": ""},
    ]


def _dump(win=None, menu=None):
    win = _win_elements() if win is None else win
    menu = _menubar_elements() if menu is None else menu
    return lambda pid: {"windows": win, "menubar": menu}


class FakeStore:
    def __init__(self):
        self.saved: list = []
        self.summary_states: list[dict] = []
        self.details: dict[str, dict] = {}
        self.transitions: list[dict] = []

    async def save_app_model(self, app):
        self.saved.append(app)
        self.summary_states = [{"id": sid, "title": s.window_title} for sid, s in app.states.items()]
        self.details = {
            sid: {"window_title": s.window_title, "elements": [e.model_dump() for e in s.elements]}
            for sid, s in app.states.items()
        }
        self.transitions = [
            {"from_state": t.from_state, "label": t.action.label, "to_state": t.to_state, "type": t.action_type}
            for t in app.transitions
        ]

    async def get_app_summary(self, bundle_id, platform="macos"):
        if not self.summary_states:
            return None
        from app.core.atlas.schemas import AtlasAppSummary

        return AtlasAppSummary(
            app_name=bundle_id, bundle_id=bundle_id, platform=platform,
            state_count=len(self.summary_states), states=self.summary_states,
        )

    async def get_state_detail(self, bundle_id, state_id, platform="macos"):
        d = self.details.get(state_id)
        if d is None:
            return None
        from app.core.atlas.schemas import AtlasStateDetail

        return AtlasStateDetail(state_id=state_id, window_title=d["window_title"], elements=d["elements"])

    async def get_transitions_summary(self, bundle_id, platform="macos"):
        return self.transitions

    async def list_apps(self):
        return []

    async def clear_all_data(self):
        pass


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture(autouse=True)
def _fake_launch(monkeypatch):
    from app.infrastructure.drivers.macos import _workspace

    monkeypatch.setattr(_workspace, "ensure_app_running", lambda bundle_id, wait_windows=20.0: 1234)


class TestPureHelpers:
    def test_signature_stable_and_orderless(self):
        a = element_signature(_win_elements())
        b = element_signature(list(reversed(_win_elements())))
        assert a == b
        assert signature_state_id(a) == signature_state_id(b)

    def test_signature_ignores_unnamed(self):
        els = _win_elements() + [
            {"role": "AXGroup", "name": "", "path": "window 1 > AXGroup 9", "bounds": [0, 0, 1, 1],
             "actions": [], "enabled": True, "shortcut": ""}
        ]
        assert element_signature(els) == element_signature(_win_elements())

    def test_jaccard(self):
        a = frozenset({1, 2, 3})
        b = frozenset({2, 3, 4})
        assert jaccard(a, b) == pytest.approx(0.5)
        assert jaccard(a, a) == 1.0
        assert jaccard(a, frozenset()) == 0.0

    def test_blacklist(self):
        assert is_blacklisted("退出登录")
        assert is_blacklisted("Delete All")
        assert is_blacklisted("抹掉此 Mac")
        assert is_blacklisted("重启")
        assert not is_blacklisted("通用")
        assert not is_blacklisted("Wi-Fi")
        assert not is_blacklisted("")

    def test_coverage_tier(self):
        assert coverage_tier({"interactive_named": 20, "named_pct": 50, "menu": 5}) == "A"
        assert coverage_tier({"interactive_named": 6, "named_pct": 10, "menu": 0}) == "B"
        assert coverage_tier({"interactive_named": 1, "named_pct": 5, "menu": 12}) == "B"
        assert coverage_tier({"interactive_named": 1, "named_pct": 5, "menu": 3}) == "C"

    def test_menubar_state(self):
        state = build_menubar_state(_menubar_elements())
        assert state.state_id == MENUBAR_STATE_ID
        assert state.is_infrastructure_only
        labels = [e.label for e in state.elements]
        assert labels == ["文件", "新建", "退出"]  # 空名 separator 被剔除
        new_item = state.elements[1]
        assert new_item.shortcut == "n"
        assert new_item.parent_menu == "AXMenu 1"
        assert new_item.metadata.extra["region"] == "menubar"
        assert new_item.is_infrastructure

    def test_menu_tree_hierarchy(self):
        tree = build_menu_tree(_menubar_elements())
        assert len(tree.menus) == 1
        f = tree.menus[0]
        assert f.label == "文件"
        assert [c.label for c in f.children] == ["新建", "退出"]
        assert f.children[0].action == "AXPress|cmd:n"

    def test_menu_reachable_pct(self):
        # 无名项=separator（现代 macOS 上也带 actions，经 System Events 交叉验证）
        assert menu_reachable_pct(_menubar_elements()) == 100.0
        sep_with_actions = [
            {"role": "AXMenuItem", "name": "", "path": "menubar > AXMenuBarItem 1 > AXMenu 1 > AXMenuItem 1",
             "bounds": [0, 0, 1, 1], "actions": ["AXPress", "AXPick"], "enabled": True, "shortcut": ""},
        ]
        assert menu_reachable_pct(sep_with_actions) == 0.0


class TestSurveyApp:
    async def test_readonly_survey(self, store):
        sv = AtlasSurveyor(store=store)
        result = await sv.survey_app(BUNDLE, dump_fn=_dump(), press_fn=lambda pid, path: False)
        assert result.error is None
        app = store.saved[0]
        assert MENUBAR_STATE_ID in app.states
        sig_states = [s for sid, s in app.states.items() if sid.startswith("sig_")]
        assert len(sig_states) == 1
        state = sig_states[0]
        assert state.window_title == "主窗口"
        save_btn = next(e for e in state.elements if e.label == "保存")
        assert save_btn.metadata.extra["actions"] == ["AXPress"]
        assert save_btn.bounds.width == 60
        assert result.coverage.tier in ("A", "B", "C")
        assert result.coverage.menu_reachable_pct == 100.0
        assert result.transitions_found == 0

    async def test_launch_failure(self, store, monkeypatch):
        from app.infrastructure.drivers.macos import _workspace

        monkeypatch.setattr(_workspace, "ensure_app_running", lambda bundle_id, wait_windows=20.0: None)
        sv = AtlasSurveyor(store=store)
        result = await sv.survey_app(BUNDLE, dump_fn=_dump())
        assert result.error == "launch failed"
        assert store.saved == []

    async def test_explore_records_transition_and_respects_blacklist(self, store):
        win_b = [
            {"role": "AXWindow", "name": "通用面板", "path": "window 1", "bounds": [0, 0, 800, 600],
             "actions": [], "enabled": True, "shortcut": ""},
            {"role": "AXButton", "name": "关于本机", "path": "window 1 > AXButton 1",
             "bounds": [10, 10, 60, 30], "actions": ["AXPress"], "enabled": True, "shortcut": ""},
        ]
        calls = {"n": 0}
        win_a = _win_elements()

        def dump(_pid):
            calls["n"] += 1
            # 第一次快照=状态 A，点击后=状态 B
            return {"windows": win_a if calls["n"] <= 1 else win_b, "menubar": _menubar_elements()}

        pressed: list[str] = []

        def press(_pid, path):
            pressed.append(path)
            return True

        sv = AtlasSurveyor(store=store)
        policy = SurveyPolicy(explore=True, max_clicks=5, click_settle_sec=0)
        result = await sv.survey_app(BUNDLE, dump_fn=dump, press_fn=press, policy=policy)

        # 只点了"通用"行；"删除所有内容"被黑名单拦截
        assert pressed == ["window 1 > AXOutline 1 > AXRow 1"]
        assert result.transitions_found == 1
        t = store.saved[0].transitions[0]
        assert t.action.label == "通用"
        assert t.from_state != t.to_state
        sig_states = [sid for sid in store.saved[0].states if sid.startswith("sig_")]
        assert len(sig_states) == 2

    async def test_explore_unnamed_row_uses_descendant_label(self, store):
        """macOS 边栏真实形态：AXRow 无名，标签在后代 AXStaticText（设置/Music）。"""
        win_a = [
            {"role": "AXWindow", "name": "设置", "path": "window 1", "bounds": [0, 0, 800, 600],
             "actions": [], "enabled": True, "shortcut": ""},
            {"role": "AXRow", "name": "", "path": "window 1 > AXOutline 1 > AXRow 1",
             "bounds": [0, 40, 200, 24], "actions": ["AXShowDefaultUI"], "enabled": True, "shortcut": ""},
            {"role": "AXStaticText", "name": "Wi-Fi", "path": "window 1 > AXOutline 1 > AXRow 1 > AXCell 1 > AXStaticText 1",
             "bounds": [8, 44, 100, 16], "actions": [], "enabled": True, "shortcut": ""},
            {"role": "AXRow", "name": "", "path": "window 1 > AXOutline 1 > AXRow 2",
             "bounds": [0, 64, 200, 24], "actions": ["AXShowDefaultUI"], "enabled": True, "shortcut": ""},
            {"role": "AXStaticText", "name": "删除所有内容", "path": "window 1 > AXOutline 1 > AXRow 2 > AXCell 1 > AXStaticText 1",
             "bounds": [8, 68, 100, 16], "actions": [], "enabled": True, "shortcut": ""},
        ]
        win_b = [
            {"role": "AXWindow", "name": "Wi-Fi 面板", "path": "window 1", "bounds": [0, 0, 800, 600],
             "actions": [], "enabled": True, "shortcut": ""},
            {"role": "AXButton", "name": "高级", "path": "window 1 > AXButton 1",
             "bounds": [10, 10, 60, 30], "actions": ["AXPress"], "enabled": True, "shortcut": ""},
        ]
        calls = {"n": 0}

        def dump(_pid):
            calls["n"] += 1
            return {"windows": win_a if calls["n"] <= 1 else win_b, "menubar": _menubar_elements()}

        pressed: list[str] = []

        def press(_pid, path):
            pressed.append(path)
            return True

        sv = AtlasSurveyor(store=store)
        policy = SurveyPolicy(explore=True, max_clicks=5, click_settle_sec=0)
        result = await sv.survey_app(BUNDLE, dump_fn=dump, press_fn=press, policy=policy)

        assert pressed == ["window 1 > AXOutline 1 > AXRow 1"]  # Wi-Fi 行；黑名单行不点
        assert result.transitions_found == 1
        assert store.saved[0].transitions[0].action.label == "Wi-Fi"

    async def test_merge_keeps_historical_states(self, store):
        sv = AtlasSurveyor(store=store)
        await sv.survey_app(BUNDLE, dump_fn=_dump(), press_fn=lambda pid, path: False)
        first_sig = [sid for sid in store.saved[0].states if sid.startswith("sig_")][0]

        # 第二次测绘看到完全不同的状态（如另一面板）
        other_win = [
            {"role": "AXWindow", "name": "另一面板", "path": "window 1", "bounds": [0, 0, 800, 600],
             "actions": [], "enabled": True, "shortcut": ""},
            {"role": "AXButton", "name": "高级", "path": "window 1 > AXButton 1",
             "bounds": [10, 10, 60, 30], "actions": ["AXPress"], "enabled": True, "shortcut": ""},
        ]
        await sv.survey_app(BUNDLE, dump_fn=_dump(win=other_win), press_fn=lambda pid, path: False)

        final = store.saved[-1]
        sig_states = [sid for sid in final.states if sid.startswith("sig_")]
        assert len(sig_states) == 2  # 历史状态未被覆盖
        assert first_sig in sig_states


class TestNeedsResurvey:
    async def test_no_drift(self, store, monkeypatch):
        sv = AtlasSurveyor(store=store)
        await sv.survey_app(BUNDLE, dump_fn=_dump(), press_fn=lambda pid, path: False)
        from app.infrastructure.drivers.macos import _workspace

        monkeypatch.setattr(_workspace, "running_pid_for_bundle", lambda bundle_id: 1234)
        monkeypatch.setattr(surveyor, "dump_app_elements", _dump())
        assert await sv.needs_resurvey(BUNDLE) is False

    async def test_drift_triggers_resurvey(self, store, monkeypatch):
        sv = AtlasSurveyor(store=store)
        await sv.survey_app(BUNDLE, dump_fn=_dump(), press_fn=lambda pid, path: False)
        from app.infrastructure.drivers.macos import _workspace

        monkeypatch.setattr(_workspace, "running_pid_for_bundle", lambda bundle_id: 1234)
        drifted = [
            {"role": "AXWindow", "name": "完全不同的界面", "path": "window 1", "bounds": [0, 0, 1, 1],
             "actions": [], "enabled": True, "shortcut": ""},
        ]
        monkeypatch.setattr(surveyor, "dump_app_elements", _dump(win=drifted))
        assert await sv.needs_resurvey(BUNDLE) is True

    async def test_not_running_needs_resurvey(self, store, monkeypatch):
        sv = AtlasSurveyor(store=store)
        await sv.survey_app(BUNDLE, dump_fn=_dump(), press_fn=lambda pid, path: False)
        from app.infrastructure.drivers.macos import _workspace

        monkeypatch.setattr(_workspace, "running_pid_for_bundle", lambda bundle_id: None)
        assert await sv.needs_resurvey(BUNDLE) is True
