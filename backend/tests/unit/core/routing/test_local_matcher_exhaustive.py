"""Exhaustive (generative, non-sampled) tests for the Layer-0 reference matcher.

Not a corpus — a generator: every template pattern × every affix combination ×
every dictionary value must resolve to its OWN action/slots (which doubles as a
cross-template collision audit), and every declarative frame × trigger literal
must resolve to None.
"""

from __future__ import annotations

import itertools

import pytest

from app.core.routing.init_spec import (
    _ALIASES,
    _DELTA_DICT,
    _KEY_DICT,
    _TEMPLATES,
    build_init_spec,
)
from app.core.routing.local_matcher import _PREFIXES, _SUFFIXES, LocalMatcher

APP_ENTRIES = [
    {"name": "微信", "pinyin": "weixin", "aliases": []},
    {"name": "微型", "pinyin": "weixing", "aliases": []},
    {"name": "维信", "pinyin": "weixin", "aliases": []},
    {"name": "QQ", "pinyin": "qq", "aliases": []},
    {"name": "网易云音乐", "pinyin": "wangyiyunyinyue", "aliases": []},
    {"name": "音乐", "pinyin": "yinyue", "aliases": []},
    {"name": "VSCode", "aliases": []},
    {"name": "Safari", "aliases": []},
    {"name": "终端", "pinyin": "zhongduan", "aliases": []},
]
USAGE_RANK = [e["name"] for e in APP_ENTRIES]
DICTS = {"app": APP_ENTRIES, "key": dict(_KEY_DICT), "delta": dict(_DELTA_DICT)}

PREFIXES = [""] + list(_PREFIXES)
SUFFIXES = [""] + list(_SUFFIXES)

SLOT_FILLINGS = {
    "app": [e["name"] for e in APP_ENTRIES],
    "delta": list(_DELTA_DICT),
    "key": list(_KEY_DICT),
    "name": ["小智", "旺财"],
}


def _fillings(slots: list[str]) -> list[dict[str, str]]:
    if not slots:
        return [{}]
    pools = [SLOT_FILLINGS[s] for s in slots]
    return [dict(zip(slots, combo, strict=True)) for combo in itertools.product(*pools)]


def _expected_slot(slot: str, raw: str) -> str:
    if slot == "app":
        return _ALIASES.get(raw, raw)
    if slot == "delta":
        return _DELTA_DICT[raw]
    if slot == "key":
        return _KEY_DICT[raw]
    return raw


@pytest.fixture
def matcher() -> LocalMatcher:
    return LocalMatcher(_TEMPLATES, DICTS, aliases=dict(_ALIASES), app_usage_rank=USAGE_RANK)


def test_generative_positives_exhaustive(matcher: LocalMatcher) -> None:
    """Every pattern × filling × affix combo must hit its own action/slots."""
    import re

    checked = 0
    for template in _TEMPLATES:
        action = template["action"]
        fixed = template.get("args") or {}
        for pattern in template["patterns"]:
            slots = re.findall(r"\{([a-z0-9_]+)\}", pattern)
            for filling in _fillings(slots):
                body = pattern
                for k, v in filling.items():
                    body = body.replace(f"{{{k}}}", v)
                for pre, suf in itertools.product(PREFIXES, SUFFIXES):
                    text = f"{pre}{body}{suf}"
                    res = matcher.match(text)
                    assert res is not None, f"漏检: {text!r} (模板 {pattern!r})"
                    got_action, got_args = res
                    assert got_action == action, (
                        f"交叉碰撞: {text!r} 期望 {action} 实得 {got_action}"
                    )
                    for k, v in fixed.items():
                        assert got_args.get(k) == v, f"{text!r}: 固定槽位 {k} 期望 {v}"
                    for k, v in filling.items():
                        assert got_args.get(k) == _expected_slot(k, v), (
                            f"{text!r}: 槽位 {k} 期望 {_expected_slot(k, v)} 实得 {got_args.get(k)}"
                        )
                    checked += 1
    assert checked > 5000, f"穷举量不足: {checked}"


def test_declarative_frames_exhaustive(matcher: LocalMatcher) -> None:
    """Every trigger literal inside declarative frames must NOT fire."""
    literals = [
        "暂停", "继续", "下一首", "上一首", "切歌", "静音", "取消静音",
        "截图", "屏幕截图", "锁屏", "再见", "结束",
    ]
    frames = [
        "我想{}", "你知道{}吗", "请问{}是什么", "为什么{}", "{}是什么",
        "{}怎么样", "关于{}的方案", "帮我写个{}的方案", "{}键坏了",
        "讲个关于{}的题", "{}的歌叫什么名字", "这个{}工具叫什么",
    ]
    checked = 0
    for literal, frame in itertools.product(literals, frames):
        text = frame.format(literal)
        assert matcher.match(text) is None, f"误报: {text!r}"
        checked += 1
    assert checked == len(literals) * len(frames)


def test_slot_pollution_exhaustive(matcher: LocalMatcher) -> None:
    """Non-dictionary slot values must NOT resolve."""
    cjk_pollution = ["车窗", "商品列表", "订单", "飞信", "微店", "围脖", "网易邮箱", "微波炉"]
    latin_pollution = ["VSCd", "Sarafi", "Firefly", "Chromium"]
    for name in cjk_pollution + latin_pollution:
        for verb in ["打开", "启动", "切换到", "关闭"]:
            assert matcher.match(f"{verb}{name}") is None, f"污染命中: {verb}{name}"


def test_pinyin_boundary_quartet(matcher: LocalMatcher) -> None:
    assert matcher.match("打开微信") == ("open_app", {"app": "微信"})  # exact
    assert matcher.match("打开微型") == ("open_app", {"app": "微型"})  # exact, NOT weixin
    assert matcher.match("打开维信") == ("open_app", {"app": "维信"})  # exact beats homophone rank
    assert matcher.match("打开威信") == ("open_app", {"app": "微信"})  # homophone, rank 微信 > 维信


def test_real_spec_audit() -> None:
    """Exhaustive audit over the REAL shipped spec (macOS app probe)."""
    spec = build_init_spec()
    matcher = LocalMatcher(
        spec.templates, spec.slot_dictionaries, aliases=spec.aliases, app_usage_rank=spec.app_usage_rank
    )

    # every literal pattern (affix-stripped forms) resolves to its action
    for template in spec.templates:
        for pattern in template["patterns"]:
            if "{" in pattern:
                continue
            res = matcher.match(pattern)
            assert res is not None and res[0] == template["action"], f"字面模板 {pattern!r} 不自洽: {res}"

    # every real app resolves 打开/关闭/切换 to its canonical name
    apps = spec.slot_dictionaries["app"]
    assert len(apps) >= 10, "真实 app 探测异常"
    for entry in apps:
        name = entry["name"]
        canonical = spec.aliases.get(name, name)
        for verb in ["打开", "关闭", "切换到"]:
            res = matcher.match(f"{verb}{name}")
            assert res is not None, f"真实 app 漏检: {verb}{name}"
            assert res[1].get("app") == canonical, f"{verb}{name} -> {res}"

    # pinyin coverage & collision audit over CJK-named entries
    from app.core.routing.local_matcher import _pinyin

    groups: dict[str, list[str]] = {}
    for entry in apps:
        name = entry["name"]
        if name.isascii():
            continue
        py = entry.get("pinyin") or _pinyin(name)
        assert py, f"{name} 缺拼音"
        groups.setdefault(py, []).append(name)
    # same-pinyin groups are tolerated (usage_rank tiebreaks); just surface them
    for py, names in groups.items():
        if len(names) > 1:
            print(f"\n  [同音组 {py}]: {names} -> usage_rank 决胜")
