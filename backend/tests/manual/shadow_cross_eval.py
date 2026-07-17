"""Cross-eval: run the third party's OWN FuzzyDictMatcher against OUR corpus.

His script showed 100% hit / 0% FP — but only on his own corpus, which
(a) contains zero typo cases despite "fuzzy solves typos" being the headline
    claim,
(b) contains zero declarative-sentence traps that actually occur in our
    production corpus,
(c) hardcodes shields ("的歌" guard, "商品列表" guard) for exactly the traps
    it does include.

    .venv/bin/python tests/manual/shadow_cross_eval.py
"""

import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "third_party_eval",
    "/Users/huangjinhuan/.gemini/antigravity/brain/45689f63-aa38-49d2-baa0-11787059ac57/scratch/shadow_fastpath_eval.py",
)
mod = importlib.util.module_from_spec(spec)
sys.modules["third_party_eval"] = mod
spec.loader.exec_module(mod)

matcher = mod.FuzzyDictMatcher(mod.APP_DICTIONARY)

# ── 1. OUR production L0 corpus (28 cases from shadow_layer0_eval.py) ──
OUR_L0 = [
    ("暂停", "play_pause"), ("别放了", "play_pause"), ("先停一下", "play_pause"),
    ("继续播放", "play_pause"), ("下一首", "next_track"), ("切歌", "next_track"),
    ("换一首", "next_track"), ("上一首", "prev_track"),
    ("音量大一点", "set_volume"), ("把声音调小一点", "set_volume"),
    ("音量最大", "set_volume"), ("声音小点", "set_volume"),
    ("把音量给我调高一点", "set_volume"),
    ("静音", "mute"), ("取消静音", "unmute"),
    ("截图", "screenshot"), ("截个图", "screenshot"), ("屏幕截图", "screenshot"),
    ("锁屏", "lock_screen"),
    # declarative traps
    ("暂停一下我的理解", None), ("下一首歌叫什么名字", None),
    ("这个截图工具叫什么", None), ("讲个关于音量的物理题", None),
    ("声音真好听", None), ("把车窗打开", None), ("我在微信里打开了链接", None),
    ("音量键坏了修一下", None), ("帮我写个静音室的方案", None),
]

# ── 2. Typo cases — his headline "fuzzy solves typos" claim, absent from his corpus ──
TYPOS = [
    ("打开威信", "open_app"),   # 微信 transposition typo
    ("打开微心", "open_app"),   # homophone typo
    ("打开VSCod", "open_app"),  # missing char
    ("打开网抑云音乐", None),   # near-miss slang, NOT the app name — should NOT fire
    ("打开商品列表", None),     # navigation, not an app
]

print("=" * 70)
print("1. 他的 FuzzyDictMatcher × 我们的 28 条生产语料")
print("=" * 70)
hit = fp = miss = 0
for text, exp in OUR_L0:
    res = matcher.match(text)
    got = res[0] if res else None
    if exp is None:
        if got is None:
            hit += 1
        else:
            fp += 1
            print(f"  FP : {text!r:22} -> {got} {res[1]}")
    elif got == exp:
        hit += 1
    else:
        miss += 1
        print(f"  MISS: {text!r:22} 期望 {exp} 实得 {got}")
print(f"  命中/正确拒绝 {hit}/28  误报 {fp}  漏/错 {miss}")

print()
print("=" * 70)
print("2. 错别字用例（他宣称 fuzzy 解决错别字，但其语料零覆盖）")
print("=" * 70)
for text, exp in TYPOS:
    res = matcher.match(text)
    got = res[0] if res else None
    mark = "OK " if got == exp else "FAIL"
    print(f"  {mark}: {text!r:18} 期望 {exp} 实得 {res}")
