"""Native app bias: explicit mention, frontmost fallback, pass-through cases."""

from app.core.routing.native_bias import apply_native_app_bias
from app.core.routing.schemas import RouteCandidate, RouteDecision


def _cand(cid: str, name: str) -> RouteCandidate:
    return RouteCandidate(id=f"macro:{cid}", type="macro", name=name, target=cid)


def _decision(macro_id: str, status: str = "routed", target_type: str = "macro") -> RouteDecision:
    return RouteDecision(
        status=status,
        target_type=target_type,
        target={"type": "macro", "id": macro_id},
        params={},
    )


CHROME = _cand("1", "Chrome 窗口>左侧与右侧")
LARK = _cand("2", "Lark 飞书>窗口>左侧与右侧")
WECHAT_ZOOM = _cand("3", "WeChat 微信>窗口>放大")
CHROME_ZOOM = _cand("4", "Chrome 窗口>放大")


class TestExplicitMention:
    def test_rival_mention_switches(self):
        d = _decision("1")
        out = apply_native_app_bias(d, [CHROME, LARK], "飞书左侧", None)
        assert out.target["id"] == "2"

    def test_picked_mention_keeps(self):
        d = _decision("1")
        out = apply_native_app_bias(d, [CHROME, LARK], "chrome左侧", None)
        assert out.target["id"] == "1"

    def test_mention_beats_frontmost(self):
        d = _decision("2")
        out = apply_native_app_bias(d, [CHROME, LARK], "飞书左侧", "Google Chrome")
        assert out.target["id"] == "2"


class TestFrontmostFallback:
    def test_bare_command_switches_to_active_app(self):
        d = _decision("1")
        out = apply_native_app_bias(d, [CHROME, LARK], "窗口放左边", "Lark")
        assert out.target["id"] == "2"

    def test_no_switch_when_active_is_picked(self):
        d = _decision("2")
        out = apply_native_app_bias(d, [CHROME, LARK], "窗口放左边", "Lark")
        assert out.target["id"] == "2"

    def test_no_switch_when_active_unknown(self):
        d = _decision("1")
        out = apply_native_app_bias(d, [CHROME, LARK], "窗口放左边", "Finder")
        assert out.target["id"] == "1"


class TestPassThrough:
    def test_non_macro_untouched(self):
        d = _decision("1", target_type="skill")
        out = apply_native_app_bias(d, [CHROME, LARK], "飞书左侧", "Lark")
        assert out.target_type == "skill"

    def test_delegate_untouched(self):
        d = _decision("1", status="delegate")
        out = apply_native_app_bias(d, [CHROME, LARK], "飞书左侧", "Lark")
        assert out.status == "delegate"

    def test_no_rival_same_leaf_untouched(self):
        d = _decision("3")
        out = apply_native_app_bias(d, [WECHAT_ZOOM, CHROME], "放大", "Google Chrome")
        assert out.target["id"] == "3"  # CHROME leaf differs -> not a rival

    def test_rival_present_switch(self):
        d = _decision("3")
        out = apply_native_app_bias(
            d, [WECHAT_ZOOM, CHROME_ZOOM], "放大窗口", "Google Chrome"
        )
        assert out.target["id"] == "4"

    def test_picked_not_in_candidates_untouched(self):
        d = _decision("99")
        out = apply_native_app_bias(d, [CHROME, LARK], "飞书左侧", "Lark")
        assert out.target["id"] == "99"

    def test_field_macro_no_leaf_untouched(self):
        field = _cand("5", "Chrome 地址栏输入")
        d = _decision("5")
        out = apply_native_app_bias(d, [field, CHROME_ZOOM], "输入网址", "WeChat")
        assert out.target["id"] == "5"
