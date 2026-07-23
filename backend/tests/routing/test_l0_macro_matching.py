"""
L0 Macro trigger matching tests.

Verifies that the LocalMatcher correctly matches builtin commands and
preset/User Macro trigger patterns, with correct conflict resolution
(preset wins on duplicate triggers).

Tests the matching layer only — no DB dependency. Directly constructs
a LocalMatcher from the combined template list.
"""

from app.core.routing.local_matcher import LocalMatcher

# ── Builtin templates (same set as init_spec after cleanup) ───
_BUILTIN_TEMPLATES = [
    {"action": "clarify", "patterns": ["再说一遍", "没听清", "重说"], "slots": {}},
    {"action": "rename", "patterns": ["你以后叫{name}", "改名{name}", "你的名字是{name}"], "slots": {"name": "str"}},
    {"action": "end", "patterns": ["再见", "拜拜", "结束", "退出对话"], "slots": {}},
    {"action": "ack", "patterns": ["对对对", "没错", "就这个", "可以", "对的", "是的"], "slots": {}},
    {"action": "cancel", "patterns": ["算了", "不用了", "不要", "取消"], "slots": {}},
]

# ── Preset Macro templates (simulating enrich_spec_with_macro_triggers output) ───
_PRESET_MACRO_TEMPLATES = [
    {"action": "macro:1", "patterns": ["静音", "别出声", "不要声音", "安静"], "slots": {}},
    {"action": "macro:2", "patterns": ["取消静音", "恢复声音", "打开声音", "不静音了"], "slots": {}},
    {"action": "macro:3", "patterns": ["音量大一点", "调高音量", "大声一点", "声音大一点", "调大音量"], "slots": {}},
    {"action": "macro:4", "patterns": ["音量小一点", "调低音量", "小声一点", "声音小一点", "调小音量"], "slots": {}},
    {"action": "macro:5", "patterns": ["音量最大", "最大声", "声音调到最大", "最大音量"], "slots": {}},
    {"action": "macro:6", "patterns": ["暂停", "继续播放", "开始播放", "继续", "接着放", "停一下", "别放了", "先停"], "slots": {}},
    {"action": "macro:7", "patterns": ["下一首", "下一曲", "切歌", "换一首", "下首歌"], "slots": {}},
    {"action": "macro:8", "patterns": ["上一首", "上一曲", "回上一首", "上一首歌"], "slots": {}},
    {"action": "macro:9", "patterns": ["截图", "截屏", "屏幕截图", "截个图", "截一下屏"], "slots": {}},
    {"action": "macro:10", "patterns": ["锁屏", "锁定屏幕", "锁电脑", "锁一下"], "slots": {}},
    {"action": "macro:11", "patterns": ["打开微信", "启动微信", "开一下微信"], "slots": {}},
    {"action": "macro:12", "patterns": ["打开Chrome", "启动Chrome", "开一下Chrome"], "slots": {}},
    {"action": "macro:13", "patterns": ["打开Safari", "启动Safari", "开一下Safari"], "slots": {}},
    {"action": "macro:14", "patterns": ["打开终端", "启动终端", "开一下终端"], "slots": {}},
    {"action": "macro:15", "patterns": ["打开Finder", "打开访达", "开一下访达"], "slots": {}},
    {"action": "macro:16", "patterns": ["打开VS Code", "打开VSCode", "启动VS Code"], "slots": {}},
    {"action": "macro:17", "patterns": ["退出微信", "关闭微信", "关掉微信"], "slots": {}},
    {"action": "macro:18", "patterns": ["退出Chrome", "关闭Chrome", "关掉Chrome"], "slots": {}},
    {"action": "macro:19", "patterns": ["退出Safari", "关闭Safari", "关掉Safari"], "slots": {}},
    {"action": "macro:20", "patterns": ["按回车", "按一下回车", "按下回车"], "slots": {}},
    {"action": "macro:21", "patterns": ["按空格", "按一下空格", "按下空格"], "slots": {}},
]


def _make_matcher(templates=None):
    templates = templates or _BUILTIN_TEMPLATES + _PRESET_MACRO_TEMPLATES
    return LocalMatcher(templates=templates)


class TestL0MacroMatching:
    """Test that each trigger pattern correctly resolves to the expected action."""

    def _check(self, text: str, expected_action: str):
        m = _make_matcher()
        result = m.match(text)
        assert result is not None, f"'{text}' 应匹配 {expected_action}"
        action, _args = result
        assert action == expected_action, f"'{text}' 应匹配 {expected_action}, 实际匹配 {action}"

    def _no_match(self, text: str):
        m = _make_matcher()
        result = m.match(text)
        assert result is None, f"'{text}' 不应被匹配"

    # ── Builtin commands ───────────────────────────────────────

    def test_builtin_clarify(self):
        for t in ["再说一遍", "没听清", "重说"]:
            self._check(t, "clarify")

    def test_builtin_end(self):
        for t in ["再见", "拜拜", "结束", "退出对话"]:
            self._check(t, "end")

    def test_builtin_ack(self):
        for t in ["对对对", "没错", "就这个", "可以"]:
            self._check(t, "ack")

    def test_builtin_cancel(self):
        for t in ["算了", "不用了", "不要", "取消"]:
            self._check(t, "cancel")

    def test_rename_with_slot(self):
        m = _make_matcher()
        result = m.match("你以后叫小明")
        assert result is not None
        action, args = result
        assert action == "rename"
        assert args.get("name") == "小明"

    # ── Preset Macro triggers ──────────────────────────────────

    def test_macro_mute(self):
        for t in ["静音", "别出声", "不要声音", "安静"]:
            self._check(t, "macro:1")

    def test_macro_unmute(self):
        for t in ["取消静音", "恢复声音", "打开声音"]:
            self._check(t, "macro:2")

    def test_macro_volume_up(self):
        for t in ["音量大一点", "调高音量", "大声一点", "声音大一点", "调大音量"]:
            self._check(t, "macro:3")

    def test_macro_volume_down(self):
        for t in ["音量小一点", "调低音量", "小声一点", "声音小一点", "调小音量"]:
            self._check(t, "macro:4")

    def test_macro_volume_max(self):
        for t in ["音量最大", "最大声"]:
            self._check(t, "macro:5")

    def test_macro_play_pause(self):
        for t in ["暂停", "继续播放", "开始播放", "继续", "接着放", "停一下", "别放了", "先停"]:
            self._check(t, "macro:6")

    def test_macro_next_track(self):
        for t in ["下一首", "下一曲", "切歌", "换一首"]:
            self._check(t, "macro:7")

    def test_macro_prev_track(self):
        for t in ["上一首", "上一曲", "回上一首"]:
            self._check(t, "macro:8")

    def test_macro_screenshot(self):
        for t in ["截图", "截屏", "屏幕截图", "截个图", "截一下屏"]:
            self._check(t, "macro:9")

    def test_macro_lock_screen(self):
        for t in ["锁屏", "锁定屏幕", "锁电脑", "锁一下"]:
            self._check(t, "macro:10")

    def test_macro_open_wechat(self):
        for t in ["打开微信", "启动微信", "开一下微信"]:
            self._check(t, "macro:11")

    def test_macro_open_terminal(self):
        for t in ["打开终端", "启动终端", "开一下终端"]:
            self._check(t, "macro:14")

    def test_macro_quit_wechat(self):
        for t in ["退出微信", "关闭微信", "关掉微信"]:
            self._check(t, "macro:17")

    def test_macro_press_enter(self):
        for t in ["按回车", "按一下回车", "按下回车"]:
            self._check(t, "macro:20")

    def test_macro_press_space(self):
        for t in ["按空格", "按一下空格", "按下空格"]:
            self._check(t, "macro:21")

    # ── Prefix/suffix stripping ────────────────────────────────

    def test_prefix(self):
        self._check("帮我静音", "macro:1")

    def test_suffix(self):
        self._check("静音一下", "macro:1")

    def test_prefix_and_suffix(self):
        self._check("帮我静音一下", "macro:1")

    def test_prefix_next(self):
        self._check("帮我下一首", "macro:7")

    # ── No-match cases ─────────────────────────────────────────

    def test_no_match_empty(self):
        self._no_match("")

    def test_no_match_nonsense(self):
        self._no_match("今天天气怎么样")

    def test_no_match_compound(self):
        """多意图语句不应命中 L0"""
        self._no_match("打开微信给张三发消息")

    def test_no_match_context(self):
        """需要上下文的语句不应命中 L0"""
        self._no_match("我上个月买的耳机在哪里")

    # ── Edge cases ─────────────────────────────────────────────

    def test_longest_literal_wins(self):
        """同前缀的 pattern 按字面量长度优先匹配"""
        m = _make_matcher()
        # "声音大一点" (5) vs "声音小一点" (5) — same length, order matters
        # But "音量最大" vs "音量小一点" — "音量小一点" is longer
        result = m.match("声音大一点")
        assert result is not None
        assert result[0] == "macro:3"

    def test_rename_with_name(self):
        m = _make_matcher()
        result = m.match("改名小明")
        assert result is not None
        action, args = result
        assert action == "rename"
        assert args.get("name") == "小明"
