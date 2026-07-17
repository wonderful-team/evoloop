"""Falsification probes for the third party's HybridMatcher (round 2).

His 100%/100% rests on PINYIN_SPEC — a hardcoded 24-entry answer table, not
pinyin conversion. Probes:

A. Homophone typos NOT pre-registered in his table (维信/围信 are real
   weixin homophones absent from PINYIN_SPEC).
B. Threshold overlap in his own table: 微型(weixing) vs 微信(weixin) is
   edit-distance 1 -> his matcher opens 微信 for "打开微型" (FP by design).
C. Coverage ceiling of anchored regex on un-enumerated natural phrasing
   (conservative fallback is acceptable, but the ceiling must be visible).

    .venv/bin/python tests/manual/shadow_hybrid_falsify.py
"""

import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "third_party_hybrid",
    "/Users/huangjinhuan/.gemini/antigravity/brain/45689f63-aa38-49d2-baa0-11787059ac57/scratch/shadow_hybrid_eval.py",
)
mod = importlib.util.module_from_spec(spec)
sys.modules["third_party_hybrid"] = mod
spec.loader.exec_module(mod)

matcher = mod.HybridMatcher(mod.APP_DICTIONARY)

print("=" * 70)
print("A. 未预登记的同音错别字（真实 pypinyin 能救，他的答案表不能）")
print("=" * 70)
for text in ["打开维信", "打开围信", "打开未信"]:
    res = matcher.match(text)
    print(f"  {text!r:12} -> {res}  {'(漏)' if res is None else ''}")

# 对照：真实拼音转换（init_spec.py 的可选依赖 pypinyin；本机未安装时跳过）
try:
    from pypinyin import lazy_pinyin
except ImportError:
    lazy_pinyin = None
    print("  (pypinyin 未安装——init_spec.py 中本为可选依赖，真实实现需补装)")

if lazy_pinyin:
    for w in ["维信", "围信", "未信", "威信", "微信"]:
        print(f"  pypinyin: {w} -> {''.join(lazy_pinyin(w))}")

print()
print("=" * 70)
print("B. 拼音编辑距离≤1 的阈值重叠（他自己表里的 微型 vs 微信）")
print("=" * 70)
for text in ["打开微型", "启动微型"]:
    res = matcher.match(text)
    print(f"  {text!r:12} -> {res}  {'<== 误开微信' if res else ''}")
print(f"  edit_distance('weixin','weixing') = {mod.edit_distance('weixin', 'weixing')}")

print()
print("=" * 70)
print("C. 锚定正则的覆盖率天花板（保守回落可接受，但要看见）")
print("=" * 70)
for text in ["把音乐暂停一下", "声音给我调到一半", "帮我把音乐关了", "截一下屏幕"]:
    res = matcher.match(text)
    print(f"  {text!r:16} -> {res}")
