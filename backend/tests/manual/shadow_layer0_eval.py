"""Shadow eval: third-party "Layer-0 dictionary intersection + template-regex"
proposal, measured on labeled corpora.

    .venv/bin/python tests/manual/shadow_layer0_eval.py

M1: template pattern-substring matching (what our client Init-Spec templates
    amount to today).
M2: proposal's verb+slot dictionary intersection (Aho-Corasick semantics,
    exact substring; "fuzzy" in the proposal is a misnomer).
M3: macro trigger_patterns compiled to regex with a query capture group
    (proposal 方案二) — coverage/precision on the 47-phrase routing corpus
    vs the current embedding+LLM path (measured 100% in §二十三~二十五).
"""

import re
import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

# ── L0 corpus: (text, expected_action or None) ───────────────
L0 = [
    ("暂停", "play_pause"), ("别放了", "play_pause"), ("先停一下", "play_pause"),
    ("继续播放", "play_pause"), ("下一首", "next_track"), ("切歌", "next_track"),
    ("换一首", "next_track"), ("上一首", "prev_track"),
    ("音量大一点", "set_volume"), ("把声音调小一点", "set_volume"),
    ("音量最大", "set_volume"), ("声音小点", "set_volume"),
    ("把音量给我调高一点", "set_volume"),
    ("静音", "mute"), ("取消静音", "unmute"),
    ("截图", "screenshot"), ("截个图", "screenshot"), ("屏幕截图", "screenshot"),
    ("锁屏", "lock_screen"),
    # traps: declarative sentences containing trigger words
    ("暂停一下我的理解", None), ("下一首歌叫什么名字", None),
    ("这个截图工具叫什么", None), ("讲个关于音量的物理题", None),
    ("声音真好听", None), ("把车窗打开", None), ("我在微信里打开了链接", None),
    ("音量键坏了修一下", None), ("帮我写个静音室的方案", None),
]

TEMPLATES = [
    {"action": "play_pause", "patterns": ["暂停", "停一下", "别放了", "先停"], "slots": {}},
    {"action": "play_pause", "patterns": ["继续", "继续播放", "接着放"], "slots": {}},
    {"action": "next_track", "patterns": ["下一首", "下一曲", "切歌", "换一首"], "slots": {}},
    {"action": "prev_track", "patterns": ["上一首", "上一曲", "回上一首"], "slots": {}},
    {"action": "set_volume", "patterns": ["音量{delta}", "声音{delta}"],
     "slots": {"delta": ["大一点", "小一点", "最大", "最小", "调高", "调低"]}},
    {"action": "mute", "patterns": ["静音"], "slots": {}},
    {"action": "unmute", "patterns": ["取消静音", "别静音"], "slots": {}},
    {"action": "screenshot", "patterns": ["截图", "截屏", "屏幕截图"], "slots": {}},
    {"action": "lock_screen", "patterns": ["锁屏"], "slots": {}},
]

# M2 verb/slot dictionary view of the same actions (proposal semantics)
DICT = [
    {"action": "play_pause", "verbs": ["暂停", "停一下", "别放了", "先停", "继续播放", "接着放"], "slots": []},
    {"action": "next_track", "verbs": ["下一首", "下一曲", "切歌", "换一首"], "slots": []},
    {"action": "prev_track", "verbs": ["上一首", "上一曲", "回上一首"], "slots": []},
    {"action": "set_volume", "verbs": ["音量", "声音"],
     "slots": ["大一点", "小一点", "最大", "最小", "调高", "调低", "小点", "大点"]},
    {"action": "mute", "verbs": ["静音"], "slots": []},
    {"action": "screenshot", "verbs": ["截图", "截屏", "屏幕截图"], "slots": []},
    {"action": "lock_screen", "verbs": ["锁屏"], "slots": []},
]


def m1_match(text: str) -> str | None:
    """Pattern-substring: pattern literals all present, slots from dict."""
    for t in TEMPLATES:
        for p in t["patterns"]:
            if "{delta}" in p:
                pre = p.split("{delta}")[0]
                if pre in text and any(s in text for s in t["slots"]["delta"]):
                    return t["action"]
            elif p in text:
                return t["action"]
    return None


def m2_match(text: str) -> str | None:
    """Proposal verb+slot intersection: slot-less actions = single-word trigger."""
    for a in DICT:
        if not any(v in text for v in a["verbs"]):
            continue
        if a["slots"] and not any(s in text for s in a["slots"]):
            continue
        return a["action"]
    return None


# ── 方案二: macro trigger template -> regex ──────────────────
MACRO_TEMPLATES = [
    (52, "查看{query}商品"), (52, "找{query}"), (52, "定位{query}商品"),
    (106, "查{query}商品库存"), (107, "查{query}商品价格"),
    (54, "改{query}商品库存"), (60, "改{query}商品价格"),
    (62, "查看{query}订单"), (110, "打开商品列表"), (118, "打开订单列表"),
]

CORPUS = [
    ("查一下夜光亚克力钥匙扣", {52}), ("帮我看看夜光亚克力钥匙扣这个商品", {52, 106, 107}),
    ("查询商品列表", {52}), ("夜光亚克力钥匙扣的详细信息", {52, 106, 107}),
    ("夜光亚克力钥匙扣还有多少库存", {106}), ("查一下夜光亚克力钥匙扣的库存", {106}),
    ("钥匙扣库存够吗", {106, 52}), ("夜光亚克力钥匙扣剩多少件", {106}),
    ("夜光亚克力钥匙扣多少钱", {107}), ("查一下夜光亚克力钥匙扣的价格", {107}),
    ("钥匙扣卖多少钱", {107}), ("夜光亚克力钥匙扣的售价是多少", {107}),
    ("把夜光亚克力钥匙扣的库存改成50", {54}), ("钥匙扣库存调到200", {54}),
    ("修改夜光亚克力钥匙扣的库存为88", {54}),
    ("把夜光亚克力钥匙扣的价格改成66", {60}), ("钥匙扣价格调到99", {60}),
    ("修改夜光亚克力钥匙扣的售价", {60}),
    ("查一下订单", {62}), ("看看最近的订单", {62}), ("订单列表给我看看", {62}),
    ("查询订单信息", {62}),
    ("查一下夜光压力克钥匙扣", {52}), ("钥匙扣裤存够吗", {106, 52}),
    ("钥匙扣卖多少钱呃", {107}), ("把夜光亚克力钥匙扣的裤存改成五十", {54}),
    ("钥匙扣价格调到九十九", {60}), ("查一下定单", {62}),
    ("打开商品列表", {110}), ("帮我打开商品列表", {110}), ("请显示商品列表", {110}),
    ("进入商品列表", {110}), ("商品列表打开一下", {110}), ("看看商品列表", {110}),
    ("今天天气怎么样", None), ("帮我写个周报", None), ("讲个笑话", None),
    ("今天天气怎摸样", None), ("帮我写个周爆", None),
]


def compile_template(tpl: str) -> re.Pattern:
    parts = tpl.split("{query}")
    pat = "(.+?)".join(re.escape(p) for p in parts)
    return re.compile(pat)


def m3_match(text: str):
    for mid, tpl in MACRO_TEMPLATES:
        m = compile_template(tpl).search(text)
        if m:
            query = m.group(1) if "{query}" in tpl else None
            return mid, query
    return None, None


def main() -> None:
    print("=" * 60)
    print("L0 本地指令：M1(模板子串) vs M2(字典交集)")
    for name, fn in (("M1", m1_match), ("M2", m2_match)):
        fp = [(t, fn(t)) for t, exp in L0 if exp is None and fn(t) is not None]
        fn_ = [t for t, exp in L0 if exp is not None and fn(t) != exp]
        hits = sum(1 for t, exp in L0 if exp is not None and fn(t) == exp)
        total = sum(1 for _, exp in L0 if exp is not None)
        print(f"\n[{name}] 命中 {hits}/{total}  误报 {len(fp)}  错/漏 {len(fn_)}")
        for t, a in fp:
            print(f"  FP: {t!r} -> {a}")
        for t in fn_:
            print(f"  MISS/WRONG: {t!r} -> {fn(t)}")

    print("\n" + "=" * 60)
    print("方案二：宏触发词编译正则的覆盖率/精度（对比现状 embedding+LLM=100%）")
    cover = wrong = 0
    missed = []
    for text, exp in CORPUS:
        mid, q = m3_match(text)
        if exp is None:
            if mid is not None:
                wrong += 1
                print(f"  FP: {text!r} -> macro {mid} query={q!r}")
            continue
        if mid in exp:
            cover += 1
        else:
            missed.append((text, mid, q))
    total = sum(1 for _, e in CORPUS if e is not None)
    print(f"  覆盖命中 {cover}/{total} = {cover / total:.0%}，垃圾误报 {wrong}")
    print(f"  未覆盖(需回落 embedding+LLM) {len(missed)} 条，示例:")
    for text, mid, q in missed[:10]:
        print(f"    {text!r} (matched={mid} q={q!r})")


if __name__ == "__main__":
    main()
