"""Unit tests for the Layer-0 reference matcher (rules of report §三十四)."""

from __future__ import annotations

import pytest

from app.core.routing.local_matcher import LocalMatcher, sorted_templates
from tests.unit.core.routing import fixtures as routing_fixtures

APP_ENTRIES = [
    {"name": "微信", "pinyin": "weixin", "aliases": []},
    {"name": "网易云音乐", "pinyin": "wangyiyunyinyue", "aliases": []},
    {"name": "音乐", "pinyin": "yinyue", "aliases": []},
    {"name": "音悦", "pinyin": "yinyue", "aliases": []},
    {"name": "VSCode", "aliases": []},
    {"name": "Safari", "aliases": []},
    {"name": "终端", "pinyin": "zhongduan", "aliases": []},
]
USAGE_RANK = ["微信", "音乐", "音悦", "网易云音乐", "VSCode", "Safari", "终端"]

SLOT_DICTIONARIES = {
    "app": APP_ENTRIES,
    "key": dict(routing_fixtures._KEY_DICT),
    "delta": dict(routing_fixtures._DELTA_DICT),
}


@pytest.fixture
def matcher() -> LocalMatcher:
    return LocalMatcher(
        routing_fixtures._TEMPLATES,
        SLOT_DICTIONARIES,
        aliases=dict(routing_fixtures._ALIASES),
        app_usage_rank=USAGE_RANK,
    )


# ── Rule 1+3: positive commands hit ──────────────────────────

POSITIVE = [
    ("暂停", "play_pause", {"state": "pause"}),
    ("别放了", "play_pause", {"state": "pause"}),
    ("先停一下", "play_pause", {"state": "pause"}),
    ("继续播放", "play_pause", {"state": "resume"}),
    ("请继续播放", "play_pause", {"state": "resume"}),
    ("下一首", "next_track", {}),
    ("切歌", "next_track", {}),
    ("换一首", "next_track", {}),
    ("上一首", "prev_track", {}),
    ("音量大一点", "set_volume", {"delta": "+10"}),
    ("把声音调小一点", "set_volume", {"delta": "-10"}),
    ("音量最大", "set_volume", {"delta": "100"}),
    ("声音小点", "set_volume", {"delta": "-10"}),
    ("把音量给我调高一点", "set_volume", {"delta": "+10"}),
    ("静音", "mute", {}),
    ("取消静音", "unmute", {}),
    ("截图", "screenshot", {}),
    ("截个图", "screenshot", {}),
    ("屏幕截图", "screenshot", {}),
    ("锁屏", "lock_screen", {}),
    ("打开微信", "open_app", {"app": "微信"}),
    ("帮我打开微信", "open_app", {"app": "微信"}),
    ("打开VSCode", "open_app", {"app": "VSCode"}),
    ("打开音乐", "open_app", {"app": "Apple Music"}),  # alias canonicalization
    ("切换到终端", "focus_app", {"app": "终端"}),
    ("按一下回车", "press_key", {"key": "Return"}),
    ("按一下回车键", "press_key", {"key": "Return"}),
    ("音量调到一半", "set_volume", {"delta": "50"}),
    ("暂停。", "play_pause", {"state": "pause"}),
    ("你以后叫小智", "rename", {"name": "小智"}),
]


@pytest.mark.parametrize(("text", "action", "args"), POSITIVE)
def test_positive_hits(matcher: LocalMatcher, text: str, action: str, args: dict) -> None:
    res = matcher.match(text)
    assert res is not None, f"{text} should match {action}"
    got_action, got_args = res
    assert got_action == action
    for k, v in args.items():
        assert got_args.get(k) == v, f"{text}: slot {k} expected {v}, got {got_args.get(k)}"


# ── Rule 1: declarative traps rejected structurally ─────────

TRAPS = [
    "暂停一下我的理解",
    "下一首歌叫什么名字",
    "这个截图工具叫什么",
    "讲个关于音量的物理题",
    "声音真好听",
    "把车窗打开",
    "我在微信里打开了链接",
    "音量键坏了修一下",
    "帮我写个静音室的方案",
    "播放周杰伦的歌",
    "打开商品列表",
    "打开微型",  # weixing != weixin: pinyin equality, not distance<=1
    # compound commands: must fall through WHOLE, never half-execute one clause
    "把音量大一点再静音",
    "暂停然后截图",
    "打开微信再锁屏",
    "先截图再锁屏",
    "静音并且锁屏",
]


@pytest.mark.parametrize("text", TRAPS)
def test_traps_rejected(matcher: LocalMatcher, text: str) -> None:
    assert matcher.match(text) is None, f"{text} must not match any local action"


# ── Rule 4: homophone / typo tolerance ───────────────────────


@pytest.mark.parametrize("typo", ["打开威信", "打开微心", "打开维信", "打开围信"])
def test_homophone_typos_resolve(matcher: LocalMatcher, typo: str) -> None:
    assert matcher.match(typo) == ("open_app", {"app": "微信"})


def test_latin_edit_distance_one(matcher: LocalMatcher) -> None:
    assert matcher.match("打开VSCod") == ("open_app", {"app": "VSCode"})


def test_near_miss_slang_resolves_to_real_app(matcher: LocalMatcher) -> None:
    # 网抑云音乐 is pinyin-identical to 网易云音乐: correct ASR tolerance.
    # (The original trap targeted substring matchers grabbing the wrong app "音乐".)
    assert matcher.match("打开网抑云音乐") == ("open_app", {"app": "网易云音乐"})


def test_usage_rank_tiebreak(matcher: LocalMatcher) -> None:
    # "打开音悦" exact-matches 音悦; homophone "打开音月" resolves by usage rank
    # between pinyin-identical 音乐 and 音悦 -> 音乐 ranks higher.
    assert matcher.match("打开音月") == ("open_app", {"app": "Apple Music"})


# ── Rule 2: shipping order ───────────────────────────────────


def test_sorted_templates_longest_first() -> None:
    ordered = sorted_templates(routing_fixtures._TEMPLATES)

    def index_of(action: str, args_key: str | None = None) -> int:
        for i, t in enumerate(ordered):
            if t["action"] != action:
                continue
            if args_key is None or (t.get("args") or {}).get("state") == args_key:
                return i
        raise AssertionError(action)

    assert index_of("unmute") < index_of("mute")
