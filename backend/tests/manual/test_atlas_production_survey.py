"""PRODUCTION-path wide-coverage survey via run_agent_background.

Runs the real engine (supervisor/worker graph, real tool wiring, real skill
library) against member-center. The app_map_analysis skill is explicitly
attached; the worker drives list_dir/grep/read_file + write_app_map itself.

Prereqs seeded into the scratch DB: LLM custom config (DashScope qwen-plus).

Run: .venv/bin/python tests/manual/test_atlas_production_survey.py
"""
import asyncio
import logging
import os

DB = "/var/folders/h7/llqy_6yj04g6t9ls9gk8kgzw0000gn/T/opencode/atlas_prod.db"
os.environ["SQLITE_PATH"] = DB
if os.path.exists(DB):
    os.remove(DB)

# keep engine logs visible (agent trajectory)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
for noisy in ("sqlalchemy", "httpx", "httpcore", "asyncio", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

BACKEND = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend"
MALL = "/Users/huangjinhuan/Projects/develop-assistant.cn/member-center/backend"
PROJECT_ID = 88


async def main():
    from dotenv import dotenv_values

    key = dotenv_values(f"{BACKEND}/../.env").get("DASHSCOPE_API_KEY")
    assert key, "DASHSCOPE_API_KEY missing"

    from app.infrastructure.database.resource_manager import db_resource_manager

    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    # ---------- seed LLM custom config ----------
    from app.infrastructure.config import SystemConfigService

    SystemConfigService.set_value("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1", "test")
    SystemConfigService.set_value("LLM_API_KEY", key, "test")
    SystemConfigService.set_value("LLM_PROVIDER_TYPE", "openai", "test")
    print("[seed] LLM custom config written (dashscope qwen-plus)")

    # ---------- import built-in skills (app_map_analysis) ----------
    from app.core.learning.discovery import skill_discovery

    await skill_discovery.ensure_system_skills_synced()

    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.learning import LearnedSkill

    async with session_scope() as db:
        rows = (await db.execute(select(LearnedSkill))).scalars().all()
    target = next((s for s in rows if "app_map" in (s.name or "").lower() or "地图" in (s.description or "")), None)
    assert target is not None, f"app_map_analysis skill not imported; have: {[s.name for s in rows]}"
    print(f"[seed] skill imported: id={target.id} name={target.name}")

    # ---------- production run ----------
    from app.core.engine.background_agent import run_agent_background

    goal = (
        "对当前项目（ThinkPHP 商城后台）做宽覆盖源码调研："
        "先自行扫描 app/shop/controller 梳理业务实体，"
        "然后逐实体按 AppMap Analysis 技能 SOP 调研并调用 write_app_map，"
        "每个实体写完地图后调用 generate_macros_from_app_map 生成宏。"
        "至少覆盖 goods、order、member 三个核心实体。"
    )
    inputs = {
        "goal": goal,
        "session_goal": goal,
        "messages": [{"role": "human", "content": goal}],
        "project_id": PROJECT_ID,
        "model": "custom-openai-qwen-plus",
        "working_directory": MALL,
        "metadata": {
            "explicit_skills": [{"id": target.id, "name": target.name}],
            "member_id": 0,
        },
    }
    print(f"[run] goal: {goal[:60]}...")
    await run_agent_background("atlas-wide-1", inputs)

    # ---------- report ----------
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    async with session_scope() as db:
        maps = (await db.execute(select(AppMap).where(AppMap.project_id == PROJECT_ID))).scalars().all()
        macros = (await db.execute(select(Macro).where(Macro.project_id == PROJECT_ID))).scalars().all()

    print("\n" + "=" * 76)
    print(f"{'entity':<16} {'v':>3} {'actions':>8} {'elements':>9} {'macros':>7}")
    print("-" * 76)
    for m in sorted(maps, key=lambda x: x.entity or ""):
        n = len([x for x in macros if x.app_map_id == m.id])
        print(f"{m.entity:<16} {m.map_version:>3} {len(m.actions or []):>8} {len(m.elements or []):>9} {n:>7}")
    print("-" * 76)
    print(f"合计: {len(maps)} 张地图, {len(macros)} 个宏候选")

    await db_resource_manager.shutdown()


asyncio.run(main())
