"""Seed 23 preset macros for L0 voice fast path.

All macros: project_id=NULL (global), status="verified", is_active=True,
parameters=[], namespace="preset", risk_tier="ui", requires_confirmation=False.

Run once::

    cd evoloop/backend && uv run python scripts/seed_preset_macros.py
"""

import asyncio
import json
import os
import sys

sys.path.append(os.getcwd())

PRESET_MACROS = [
    {
        "name": "mute",
        "description": "静音系统音量",
        "trigger_patterns": ["静音", "别出声", "不要声音", "安静"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume with output muted\n",
    },
    {
        "name": "unmute",
        "description": "取消静音",
        "trigger_patterns": ["取消静音", "恢复声音", "打开声音", "不静音了"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume without output muted\n",
    },
    {
        "name": "volume_up",
        "description": "音量调大",
        "trigger_patterns": ["音量大一点", "调高音量", "大声一点", "声音大一点", "调大音量"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume output volume ((output volume of (get volume settings)) + 10)\n",
    },
    {
        "name": "volume_down",
        "description": "音量调小",
        "trigger_patterns": ["音量小一点", "调低音量", "小声一点", "声音小一点", "调小音量"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume output volume ((output volume of (get volume settings)) - 10)\n",
    },
    {
        "name": "volume_max",
        "description": "音量最大",
        "trigger_patterns": ["音量最大", "最大声", "声音调到最大", "最大音量"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume output volume 100\n",
    },
    {
        "name": "volume_mid",
        "description": "音量一半",
        "trigger_patterns": ["音量一半", "音量中等", "声音一半"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume output volume 50\n",
    },
    {
        "name": "volume_min",
        "description": "音量最小",
        "trigger_patterns": ["音量最小", "最小声"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: set volume output volume 0\n",
    },
    {
        "name": "play_pause",
        "description": "播放或暂停",
        "trigger_patterns": ["暂停", "继续播放", "开始播放", "继续", "接着放", "停一下", "别放了", "先停"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"System Events\" to key code 16'\n",
    },
    {
        "name": "next_track",
        "description": "下一首",
        "trigger_patterns": ["下一首", "下一曲", "切歌", "换一首", "下首歌"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"System Events\" to key code 17'\n",
    },
    {
        "name": "prev_track",
        "description": "上一首",
        "trigger_patterns": ["上一首", "上一曲", "回上一首", "上一首歌"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"System Events\" to key code 15'\n",
    },
    {
        "name": "screenshot",
        "description": "截图",
        "trigger_patterns": ["截图", "截屏", "屏幕截图", "截个图", "截一下屏"],
        "macro_script": "- type: action\n  event_type: screenshot\n  source: desktop\n",
    },
    {
        "name": "lock_screen",
        "description": "锁屏",
        "trigger_patterns": ["锁屏", "锁定屏幕", "锁电脑", "锁一下"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"System Events\" to keystroke \"q\" using command down'\n",
    },
    {
        "name": "open_wechat",
        "description": "打开微信",
        "trigger_patterns": ["打开微信", "启动微信", "开一下微信"],
        "macro_script": "- type: action\n  event_type: open_app\n  source: desktop\n  payload:\n    app_name: WeChat\n",
    },
    {
        "name": "open_chrome",
        "description": "打开 Chrome 浏览器",
        "trigger_patterns": ["打开Chrome", "启动Chrome", "开一下Chrome"],
        "macro_script": "- type: action\n  event_type: open_app\n  source: desktop\n  payload:\n    app_name: Chrome\n",
    },
    {
        "name": "open_safari",
        "description": "打开 Safari 浏览器",
        "trigger_patterns": ["打开Safari", "启动Safari", "开一下Safari"],
        "macro_script": "- type: action\n  event_type: open_app\n  source: desktop\n  payload:\n    app_name: Safari\n",
    },
    {
        "name": "open_terminal",
        "description": "打开终端",
        "trigger_patterns": ["打开终端", "启动终端", "开一下终端"],
        "macro_script": "- type: action\n  event_type: open_app\n  source: desktop\n  payload:\n    app_name: Terminal\n",
    },
    {
        "name": "open_finder",
        "description": "打开 Finder",
        "trigger_patterns": ["打开Finder", "打开访达", "开一下访达"],
        "macro_script": "- type: action\n  event_type: open_app\n  source: desktop\n  payload:\n    app_name: Finder\n",
    },
    {
        "name": "open_vscode",
        "description": "打开 VS Code",
        "trigger_patterns": ["打开VS Code", "打开VSCode", "启动VS Code"],
        "macro_script": "- type: action\n  event_type: open_app\n  source: desktop\n  payload:\n    app_name: Visual Studio Code\n",
    },
    {
        "name": "quit_wechat",
        "description": "退出微信",
        "trigger_patterns": ["退出微信", "关闭微信", "关掉微信"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"WeChat\" to quit'\n",
    },
    {
        "name": "quit_chrome",
        "description": "退出 Chrome 浏览器",
        "trigger_patterns": ["退出Chrome", "关闭Chrome", "关掉Chrome"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"Chrome\" to quit'\n",
    },
    {
        "name": "quit_safari",
        "description": "退出 Safari 浏览器",
        "trigger_patterns": ["退出Safari", "关闭Safari", "关掉Safari"],
        "macro_script": "- type: action\n  event_type: applescript\n  source: desktop\n  payload:\n    script: 'tell application \"Safari\" to quit'\n",
    },
    {
        "name": "press_enter",
        "description": "按回车键",
        "trigger_patterns": ["按回车", "按一下回车", "按下回车"],
        "macro_script": "- type: action\n  event_type: key_press\n  source: desktop\n  payload:\n    key: Return\n",
    },
    {
        "name": "press_space",
        "description": "按空格键",
        "trigger_patterns": ["按空格", "按一下空格", "按下空格"],
        "macro_script": "- type: action\n  event_type: key_press\n  source: desktop\n  payload:\n    key: Space\n",
    },
]


async def seed():
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=False)

    from app.infrastructure.database.sql.database import session_scope
    from app.models.macro import Macro
    from app.utils.time import utcnow
    from sqlmodel import select

    async with session_scope() as session:
        existing = (await session.execute(select(Macro.name).where(Macro.namespace == "preset"))).scalars().all()
        existing_set = set(existing)

        inserted = 0
        skipped = 0
        for data in PRESET_MACROS:
            if data["name"] in existing_set:
                print(f"  ⏭  {data['name']} — 已存在")
                skipped += 1
                continue
            macro = Macro(
                name=data["name"],
                description=data["description"],
                trigger_patterns=data["trigger_patterns"],
                parameters=[],
                macro_script=data["macro_script"],
                risk_tier="ui",
                requires_confirmation=False,
                allow_self_healing=False,
                status="verified",
                is_active=True,
                namespace="preset",
                project_id=None,
                member_id=0,
                created_at=utcnow(),
            )
            session.add(macro)
            inserted += 1

        await session.commit()
        print(f"\n✅ 预置 Macro: {inserted} 条插入, {skipped} 条已跳过")


if __name__ == "__main__":
    asyncio.run(seed())
