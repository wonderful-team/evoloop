"""Final shadow eval: the shipped LocalMatcher (rules §三十四) on the EXPANDED
hand-labeled corpus (~130 cases, 9 categories, per-category stats).

    .venv/bin/python tests/manual/shadow_final_matcher_eval.py

Generative exhaustive coverage (8736 combos) lives in
tests/unit/core/routing/test_local_matcher_exhaustive.py — this file is the
auditable hand-labeled counterpart.
"""

import re
import sys
import time

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

from tests.unit.core.routing import fixtures as routing_fixtures
from app.core.routing.init_spec import build_init_spec
from app.core.routing.local_matcher import LocalMatcher, sorted_templates

APP_ENTRIES = [
    {"name": "微信", "pinyin": "weixin", "aliases": []},
    {"name": "QQ", "pinyin": "qq", "aliases": []},
    {"name": "网易云音乐", "pinyin": "wangyiyunyinyue", "aliases": []},
    {"name": "音乐", "pinyin": "yinyue", "aliases": []},
    {"name": "VSCode", "aliases": []},
    {"name": "Chrome", "aliases": []},
    {"name": "Safari", "aliases": []},
    {"name": "终端", "pinyin": "zhongduan", "aliases": []},
]
USAGE_RANK = [e["name"] for e in APP_ENTRIES]

matcher = LocalMatcher(
    sorted_templates(routing_fixtures._TEMPLATES),
    {"app": APP_ENTRIES, "key": dict(routing_fixtures._KEY_DICT), "delta": dict(routing_fixtures._DELTA_DICT)},
    aliases=dict(routing_fixtures._ALIASES),
    app_usage_rank=USAGE_RANK,
)

# (text, expected_action or None) — None = must fall through to Layer 1.
CATEGORIES: dict[str, list[tuple[str, str | None]]] = {
    "A.裸指令(全部无槽字面量)": [
        ("暂停", "play_pause"), ("停一下", "play_pause"), ("别放了", "play_pause"),
        ("先停", "play_pause"), ("继续", "play_pause"), ("继续播放", "play_pause"),
        ("接着放", "play_pause"), ("下一首", "next_track"), ("下一曲", "next_track"),
        ("切歌", "next_track"), ("换一首", "next_track"), ("上一首", "prev_track"),
        ("上一曲", "prev_track"), ("回上一首", "prev_track"),
        ("静音", "mute"), ("别出声", "mute"), ("取消静音", "unmute"),
        ("恢复声音", "unmute"), ("截图", "screenshot"), ("截屏", "screenshot"),
        ("屏幕截图", "screenshot"), ("截个图", "screenshot"),
        ("锁屏", "lock_screen"), ("锁定屏幕", "lock_screen"), ("锁电脑", "lock_screen"),
        ("再说一遍", "clarify"), ("没听清", "clarify"), ("重说", "clarify"),
        ("再见", "end"), ("拜拜", "end"), ("结束", "end"), ("退出对话", "end"),
    ],
    "B.语气词变体": [
        ("请暂停", "play_pause"), ("暂停吧", "play_pause"), ("帮我截图", "screenshot"),
        ("先停一下", "play_pause"), ("请继续播放", "play_pause"),
        ("下一首吧", "next_track"), ("帮我锁屏", "lock_screen"),
        ("把音量调大一点", "set_volume"), ("请取消静音", "unmute"),
        ("截个图吧", "screenshot"), ("麻烦锁屏", "lock_screen"),
        ("给我截图", "screenshot"), ("帮忙截图", "screenshot"),
        ("音量小一点吧", "set_volume"), ("请按一下回车", "press_key"),
        ("把声音调低一点吧", "set_volume"),
    ],
    "C.音量/按键槽位": [
        ("音量大一点", "set_volume"), ("音量大点", "set_volume"),
        ("声音响一点", "set_volume"), ("把音量调高", "set_volume"),
        ("声音调低", "set_volume"), ("音量最大", "set_volume"),
        ("音量最小", "set_volume"), ("音量一半", "set_volume"),
        ("声音小点", "set_volume"), ("把音量给我调高一点", "set_volume"),
        ("音量调到一半", "set_volume"),
        ("按回车", "press_key"), ("按一下空格", "press_key"),
        ("按下Esc", "press_key"), ("按Tab", "press_key"),
        ("按一下Command+C", "press_key"), ("按下Command+Q", "press_key"),
    ],
    "D.app打开/切换/退出": [
        ("打开微信", "open_app"), ("启动微信", "open_app"), ("开一下QQ", "open_app"),
        ("打开VSCode", "open_app"), ("打开Safari", "open_app"),
        ("打开Chrome浏览器", "open_app"), ("打开网易云音乐", "open_app"),
        ("切换到终端", "focus_app"), ("切到微信", "focus_app"),
        ("回到终端", "focus_app"), ("退出微信", "quit_app"),
        ("关闭QQ", "quit_app"), ("关掉终端", "quit_app"),
        ("帮我打开VSCode", "open_app"),
    ],
    "E.同音/错别字": [
        ("打开威信", "open_app"), ("打开微心", "open_app"), ("打开维信", "open_app"),
        ("打开围信", "open_app"), ("打开未信", "open_app"), ("打开薇信", "open_app"),
        ("打开威信吧", "open_app"), ("帮我打开威信", "open_app"),
        ("打开VSCod", "open_app"), ("打开VSCodee", "open_app"),
        ("打开网抑云音乐", "open_app"),
        ("打开终湍", None),  # 湍 tuan != duan：非谐音必须拒
    ],
    "F.陈述句陷阱": [
        ("暂停一下我的理解", None), ("下一首歌叫什么名字", None),
        ("这个截图工具叫什么", None), ("讲个关于音量的物理题", None),
        ("声音真好听", None), ("把车窗打开", None),
        ("我在微信里打开了链接", None), ("音量键坏了修一下", None),
        ("帮我写个静音室的方案", None), ("播放周杰伦的歌", None),
        ("打开商品列表", None), ("我觉得暂停一下比较好", None),
        ("你刚才说的截图功能", None), ("静音模式怎么关闭", None),
        ("上一首歌叫什么", None), ("帮我分析一下锁屏的原理", None),
        ("截图软件的优缺点", None), ("继续播放的英文怎么说", None),
        ("别出声这三个字的寓意", None), ("取消静音的快捷键是什么", None),
        ("锁屏壁纸怎么换", None), ("截屏是什么意思", None),
        ("音量单位是分贝", None), ("声音的传播速度", None),
        ("再见用英语怎么说", None), ("拜拜用英语怎么说", None),
        ("结束的近义词", None), ("退出对话流的设计", None),
    ],
    "G.复合句(必须整体回落L1，不许半截执行)": [
        ("暂停然后截图", None), ("打开微信再锁屏", None),
        ("先截图再锁屏", None), ("静音并且锁屏", None),
        ("打开微信和QQ", None), ("截图锁屏", None),
        ("暂停一下然后继续播放", None), ("把音量大一点再静音", None),
        ("先停一下再截图", None),
    ],
    "H.边界/标点/空白": [
        ("", None), ("  ", None), ("暂停。", "play_pause"),
        ("，暂停", "play_pause"), ("暂停！", "play_pause"),
        ("截图？", "screenshot"), (" 锁屏 ", "lock_screen"),
    ],
    "I.英文/数字混排": [
        ("open微信", None), ("音量调到50", None),
        ("音量三分之一", None), ("把声音turn", None),
        ("按F1", None),
    ],
}

grand = ok = fp = miss = 0
for cat, cases in CATEGORIES.items():
    c_ok = c_fp = c_miss = 0
    for text, exp in cases:
        res = matcher.match(text)
        got = res[0] if res else None
        if exp is None:
            if got is None:
                c_ok += 1
            else:
                c_fp += 1
                print(f"  FP   [{cat[:1]}] {text!r:22} -> {res}")
        elif got == exp:
            c_ok += 1
        else:
            c_miss += 1
            print(f"  MISS [{cat[:1]}] {text!r:22} 期望 {exp} 实得 {got}")
    grand += len(cases)
    ok += c_ok
    fp += c_fp
    miss += c_miss
    print(f"{cat:34} {c_ok}/{len(cases)}" + (f"  (FP {c_fp} MISS {c_miss})" if c_fp or c_miss else ""))

print(f"\n总计 {ok}/{grand}  误报 {fp}  漏/错 {miss}")

flat = [c for cases in CATEGORIES.values() for c in cases]
t0 = time.perf_counter()
for _ in range(1000):
    for text, _ in flat:
        matcher.match(text)
dur = (time.perf_counter() - t0) * 1000 / (1000 * len(flat))
print(f"平均单次匹配延迟: {dur:.4f} ms ({len(flat)} 条)")

# sanity: build_init_spec ships sorted templates with pinyin
spec = build_init_spec()
lens = []
for t in spec.templates:
    body = max((re.sub(r"\{[a-z0-9_]+\}", "", p) for p in t["patterns"]), key=len)
    lens.append(len(body))
apps = spec.slot_dictionaries["app"]
print(f"init_spec 发货模板数 {len(spec.templates)}，最长字面优先: {lens == sorted(lens, reverse=True)}")
print(f"app 条目拼音覆盖率: {sum(1 for a in apps if a.get('pinyin'))}/{len(apps)}")
