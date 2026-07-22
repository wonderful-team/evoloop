"""Shadow eval: NLU (NLTagger) vs regex in the two deterministic gates.

    .venv/bin/python tests/manual/shadow_nlu_eval.py

Measures, on labeled corpora:
  A. Detection gate (decompose trigger): current connector-regex vs
     OR-gate(regex OR nlu_verb_count>=2), raw and with the
     "verb preceded by a noun is compound-noun debris" tweak.
     Labels: single (must stay single — false compound costs an LLM call
     + decompose rewrite risk) / compound (must trigger).
  B. Substitution (anaphora rewrite): regex-only vs regex+NLU-veto
     (veto = NLU does not tag a Pronoun at the regex hit position).
     Labels: should_substitute True/False.
"""

import sys

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

import NaturalLanguage as NL

from app.core.routing import session_frame
from app.core.routing.session_frame import SessionFrame, has_connector, resolve_anaphora

FRAME = SessionFrame(current_entity={"query": "夜光亚克力钥匙扣"})

# ── corpus A: detection gate ─────────────────────────────────
SINGLES = [
    # hitrate 25
    "查一下夜光亚克力钥匙扣", "帮我看看夜光亚克力钥匙扣这个商品", "查询商品列表",
    "夜光亚克力钥匙扣的详细信息", "夜光亚克力钥匙扣还有多少库存",
    "查一下夜光亚克力钥匙扣的库存", "钥匙扣库存够吗", "夜光亚克力钥匙扣剩多少件",
    "夜光亚克力钥匙扣多少钱", "查一下夜光亚克力钥匙扣的价格", "钥匙扣卖多少钱",
    "夜光亚克力钥匙扣的售价是多少", "把夜光亚克力钥匙扣的库存改成50",
    "钥匙扣库存调到200", "修改夜光亚克力钥匙扣的库存为88",
    "把夜光亚克力钥匙扣的价格改成66", "钥匙扣价格调到99", "修改夜光亚克力钥匙扣的售价",
    "查一下订单", "看看最近的订单", "订单列表给我看看", "查询订单信息",
    "今天天气怎么样", "帮我写个周报", "讲个笑话",
    # noise 22
    "查一下夜光压力克钥匙扣", "查一下夜光亚克力要是扣", "帮我看看夜光亚克力钥匙扣那个",
    "夜光压力克钥匙扣还有多少裤存", "查一下夜光亚克力钥匙扣的裤存", "钥匙扣裤存够吗",
    "夜光亚克力钥匙扣剩多少件嗯", "夜光压力克钥匙扣多少钱", "查一下夜光亚克力钥匙扣的价各",
    "钥匙扣卖多少钱呃", "夜光亚克力钥匙扣的售假是多少",
    "把夜光亚克力钥匙扣的裤存改成五十", "钥匙扣裤存调到两百",
    "修改夜光压力克钥匙扣的库存为88", "把夜光亚克力钥匙扣的价各改成六十六",
    "钥匙扣价格调到九十九", "把钥匙扣的价格降成59",
    "查一下定单", "看看最近的订但", "定单列表给我看看", "今天天气怎摸样", "帮我写个周爆",
    # navigation + multiturn singles + entity-name traps
    "打开商品列表", "帮我打开商品列表", "请显示商品列表", "进入商品列表",
    "商品列表打开一下", "看看商品列表",
    "把它的库存改成142", "它的价格改成10", "查一下它的价格", "给他备注一下",
    "查一下吉他的价格", "把维他奶下架", "维也纳沙发多少钱", "把其他的都删了",
]
COMPOUNDS = [
    "查一下夜光亚克力钥匙扣，然后查一下订单",
    "查夜光亚克力钥匙扣，然后把它的库存改成123",
    "查夜光亚克力钥匙扣的价格，然后把它降10%",
    "查一下钥匙扣库存改成142",          # 无连接词
    "看看订单再把钥匙扣下架",            # 再
    "查库存改价格",                      # 极端无连接词
    "先把价格查了，接着把库存也改了",     # 接着
    "查一下订单，并且把钥匙扣价格调低",   # 并且
]

# ── corpus B: substitution ───────────────────────────────────
# (text, should_substitute)
SUBST = [
    ("把它的库存改成142", True), ("它的价格改成10", True), ("查一下它的价格", True),
    ("给他备注一下", True), ("将这个下架", True), ("应该把它下架", True),
    ("这个多少钱", True), ("这个商品多少钱", True), ("该订单备注一下", True),
    ("查一下吉他的价格", False), ("把维他奶下架", False), ("维也纳沙发多少钱", False),
    ("把其他的都删了", False), ("他多少钱", False),
    ("莎她娜的围巾多少钱", False),   # 黑名单未覆盖的新实体名
    ("把爱它宠物粮下架", False),     # 含"它"的品牌名
]


def nlu_tokens(text: str):
    tagger = NL.NLTagger.alloc().initWithTagSchemes_([NL.NLTagSchemeLexicalClass])
    tagger.setString_(text)
    ns = tagger.string()
    idx, out = 0, []
    while idx < len(ns):
        r = tagger.tokenRangeAtIndex_unit_(idx, NL.NLTokenUnitWord)
        tok = str(ns)[r.location: r.location + r.length]
        tag = tagger.tagAtIndex_unit_scheme_tokenRange_(
            r.location, NL.NLTokenUnitWord, NL.NLTagSchemeLexicalClass, None
        )
        out.append({"text": tok, "tag": str(tag) if tag else None,
                    "start": r.location, "end": r.location + r.length})
        idx = r.location + r.length
    return out


def nlu_verb_count(text: str, tweak: bool) -> int:
    toks = nlu_tokens(text)
    n = 0
    for i, t in enumerate(toks):
        if t["tag"] != "Verb":
            continue
        if tweak and i > 0 and toks[i - 1]["tag"] == "Noun" and toks[i - 1]["end"] == t["start"]:
            continue  # 复合名词碎片（钥匙+扣:Verb、商品+列表:Verb）
        n += 1
    return n


def nlu_has_pronoun_at(text: str, pos: int) -> bool:
    return any(t["tag"] == "Pronoun" and t["start"] == pos for t in nlu_tokens(text))


def main() -> None:
    session_frame.set_domain_nouns({"商品", "订单", "会员"})

    # ── A: detection gate ────────────────────────────────────
    print("=" * 60)
    print("A. 检测门（decompose 触发）")
    for tweak in (False, True):
        fp = []  # singles wrongly flagged compound
        fn = []  # compounds missed
        for s in SINGLES:
            gate = has_connector(s) or nlu_verb_count(s, tweak) >= 2
            if gate:
                fp.append(s)
        for s in COMPOUNDS:
            gate = has_connector(s) or nlu_verb_count(s, tweak) >= 2
            if not gate:
                fn.append(s)
        label = "OR门(原始动词数)" if not tweak else "OR门(名词后动词不计)"
        print(f"\n[{label}] singles={len(SINGLES)} compounds={len(COMPOUNDS)}")
        print(f"  误报(单句误判多意图): {len(fp)}")
        for s in fp:
            print(f"    FP: {s}")
        print(f"  漏报(多意图未检出): {len(fn)}")
        for s in fn:
            print(f"    FN: {s}")

    # regex-only baseline
    fp_r = [s for s in SINGLES if has_connector(s)]
    fn_r = [s for s in COMPOUNDS if not has_connector(s)]
    print(f"\n[regex 基线] 误报 {len(fp_r)}: {fp_r}")
    print(f"[regex 基线] 漏报 {len(fn_r)}: {fn_r}")

    # ── B: substitution with NLU veto ────────────────────────
    print("\n" + "=" * 60)
    print("B. 指代替换：regex-only vs regex+NLU否决")

    changed_by_veto = 0
    for text, truth in SUBST:
        out_regex = resolve_anaphora(text, FRAME)
        hit_regex = out_regex != text
        # veto: if regex hit, check NLU agrees there's a pronoun at hit pos
        final = out_regex
        if hit_regex:
            m = session_frame._ANAPHORA_RE.search(text)
            if m and not nlu_has_pronoun_at(text, m.start()):
                # compound tokens (这个商品等) aren't pronouns — NLU veto
                # applies only to bare 它/他/她 hits
                if m.group() in ("它", "他", "她"):
                    final = text
                    changed_by_veto += 1
        ok_r = hit_regex == truth
        ok_f = (final != text) == truth
        mark = "  " if ok_r == ok_f else ("veto修正" if ok_f else "veto误伤!")
        print(f"  [{'OK' if ok_f else 'BAD'}] {text!r:22} truth={truth} regex={hit_regex} veto后={final != text} {mark}")
    print(f"\nveto 改变判定 {changed_by_veto} 次")


if __name__ == "__main__":
    main()
