"""
L0 matching performance benchmark.

Measures LocalMatcher matching speed for all preset macros and builtin
commands across multiple iterations. No backend required.
"""

import time

from app.core.routing.local_matcher import LocalMatcher
from tests.unit.core.routing import fixtures as routing_fixtures

# All possible trigger phrases from builtin + preset templates
_ALL_PATTERNS = []
for t in routing_fixtures._TEMPLATES:
    _ALL_PATTERNS.extend(t.get("patterns", []))

# Distractors: utterances that should NOT match
_DISTRACTORS = [
    "今天天气怎么样",
    "帮我查一下明天的天气",
    "给张三发消息说今晚吃饭",
    "我上个月买的耳机在哪里",
    "打开微信给张三发消息",
    "帮我写一封邮件给老板",
    "搜索一下人工智能的最新新闻",
    "把这段文字翻译成英文",
    "这个商品的价格是多少",
    "帮我预约明天下午三点的会议室",
]


def _make_matcher():
    templates = routing_fixtures._TEMPLATES.copy()
    # Add preset macro templates (simulating enrich_spec_with_macro_triggers output)
    macros = [
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
        {"action": "macro:20", "patterns": ["按回车", "按一下回车", "按下回车"], "slots": {}},
    ]
    templates.extend(macros)
    return LocalMatcher(templates=templates)


def test_matching_accuracy():
    """Verify every concrete trigger pattern produces the expected action."""
    m = _make_matcher()
    errors = []
    for tpl in routing_fixtures._TEMPLATES:
        expected = tpl["action"]
        for pattern in tpl.get("patterns", []):
            if "{" in pattern:
                continue  # slotted patterns need concrete values; tested elsewhere
            result = m.match(pattern)
            if result is None:
                errors.append(f"'{pattern}' → 未匹配 (期望 {expected})")
            elif result[0] != expected:
                errors.append(f"'{pattern}' → {result[0]} (期望 {expected})")

    assert not errors, "\n".join(errors[:10])


def test_no_false_positives():
    """Verify distractor utterances do NOT match L0."""
    m = _make_matcher()
    false_positives = []
    for d in _DISTRACTORS:
        result = m.match(d)
        if result is not None:
            false_positives.append(f"'{d}' → 误匹配 {result[0]}")

    assert not false_positives, "\n".join(false_positives[:5])


def test_matching_speed():
    """Measure matching speed: batch of all patterns + distractors.

    Target: < 50ms for the entire batch (≈2μs per pattern).
    """
    m = _make_matcher()
    queries = _ALL_PATTERNS + _DISTRACTORS + [f"帮我{p}" for p in _ALL_PATTERNS[:10]]
    n = len(queries)

    # Warm-up
    for _ in range(100):
        m.match("静音")

    # Timed run
    t0 = time.perf_counter()
    iterations = 1000
    for _ in range(iterations):
        for q in queries:
            m.match(q)
    elapsed = time.perf_counter() - t0

    total_matches = n * iterations
    avg_us = (elapsed / total_matches) * 1_000_000
    batch_ms = elapsed / iterations * 1000

    print(f"\n  Queries per iteration: {n}")
    print(f"  Iterations: {iterations}")
    print(f"  Total matches: {total_matches:,}")
    print(f"  Total time: {elapsed:.3f}s")
    print(f"  Per match: {avg_us:.1f}μs")
    print(f"  Per iteration (all {n} queries): {batch_ms:.2f}ms")

    assert batch_ms < 50, f"Too slow: {batch_ms:.2f}ms per iteration"
