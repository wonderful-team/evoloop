#!/usr/bin/env python3
"""
Atlas AppMap Wide Survey — Full Lifecycle Integration Test

Mirrors the production path end-to-end: REAL dev DB + REAL EvoCloud login +
REAL supervisor/worker loop + REAL Huey worker consuming macro-synthesis
tasks. No mocks. Asserts on app_maps / macros rows produced by the Agent.

Skill attachment uses the production mechanism: a skill reference in the
dispatch call → metadata["explicit_skills"] → supervisor routes with
skill_ids → worker SOP injection.

FIXED PARAMETERS:
  - project_id: 21 (mall-backend repository)
  - project_path: ~/Projects/mall-backend (ThinkPHP mall admin)
  - timeout: 3600s

Run: .venv/bin/python tests/manual/test_atlas_survey_lifecycle.py
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

TEST_PROJECT_ID = 21
TEST_PROJECT_PATH = os.path.expanduser("~/Projects/mall-backend")
TEST_TIMEOUT = 10800
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
WORKER_LOG = "/tmp/atlas_survey_worker.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("atlas_survey_test")


async def _login_and_store_token(
    username: str = "preterchan", password: str = "hellomylife"
) -> str:
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning(f"[Test] EvoCloud init issues: {e}")

    client = evocloud_manager.api
    logger.info(f"[Test] Logging in via EvoCloud as {username}...")
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    await identity_service.set_token(token, login_res.get("refresh_token", ""))
    member_id = await identity_service.get_member_id(token)
    logger.info(f"[Test] Login successful. member_id={member_id}")
    return token


async def _init_backend():
    from app.infrastructure.database.resource_manager import db_resource_manager

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    await _login_and_store_token()

    from app.core.environment import awaken

    logger.info("[Test] Awakening agent environment...")
    await awaken()
    logger.info("[Test] Agent environment ready.")


async def _clear_existing_maps():
    from sqlalchemy import delete

    from app.infrastructure.database import session_scope
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    async with session_scope() as db:
        r1 = await db.execute(delete(Macro).where(Macro.project_id == TEST_PROJECT_ID))
        r2 = await db.execute(
            delete(AppMap).where(AppMap.project_id == TEST_PROJECT_ID)
        )
        logger.info(
            f"[Test] Cleared {r2.rowcount} app_maps, {r1.rowcount} macros "
            f"for project {TEST_PROJECT_ID}"
        )


async def _ensure_skill():
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.learning.skill_importer import SkillImporter
    from app.infrastructure.database import session_scope
    from app.models.learning import LearnedSkill

    logger.info("[Test] Importing built-in skills...")
    await SkillImporter.import_from_directory(settings.SKILLS_DIR)

    async with session_scope() as db:
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "AppMap Analysis",
            LearnedSkill.is_active.is_(True),
        )
        skill = (await db.execute(stmt)).scalar_one_or_none()
    if skill:
        logger.info(f"[Test] AppMap Analysis skill ready (id={skill.id})")
    else:
        logger.warning("[Test] AppMap Analysis skill not found!")
    return skill


def _start_worker() -> subprocess.Popen:
    logger.info("[Test] Starting Huey worker (real consumer)...")
    log_f = open(WORKER_LOG, "w")
    proc = subprocess.Popen(
        [os.path.join(BACKEND_DIR, ".venv/bin/python"), "-m", "bin.run_worker"],
        cwd=BACKEND_DIR,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    time.sleep(8)
    if proc.poll() is not None:
        raise RuntimeError(
            f"Worker exited early (code {proc.returncode}); see {WORKER_LOG}"
        )
    logger.info(f"[Test] Worker pid={proc.pid}, log={WORKER_LOG}")
    return proc


async def _run_survey_agent(skill, timeout: int) -> str:
    from app.core.context import thread_context_store
    from app.core.engine.dispatch import dispatch_agent_run

    thread_id = f"atlas-survey-{TEST_PROJECT_ID}-{int(time.time())}"
    # Pre-seed working directory + active project so dispatch skips path
    # resolution (mall-backend has no .evoloop/project.json yet).
    thread_context_store.set_working_directory(thread_id, TEST_PROJECT_PATH)
    thread_context_store.set_active_project(thread_id, TEST_PROJECT_ID)

    message = (
        f"**Mission Goal**: Wide-coverage source survey of the ThinkPHP mall "
        f"admin at {TEST_PROJECT_PATH} — via MECHANICAL collection, NOT "
        "manual file-by-file reading.\n"
        f"IMPORTANT: Use ABSOLUTE paths (starting with {TEST_PROJECT_PATH}) "
        "for ALL tool calls (list_dir/read_file/grep_search/find_files/"
        "write_file/execute_command). Relative paths trigger a security "
        "gate that PAUSES the entire mission. Use project-relative paths "
        "ONLY inside write_app_map citations.\n"
        "Follow this strategy STRICTLY:\n"
        "1. RECON (budget: at most 10 read/grep calls): study 2-3 sample "
        f"controllers (e.g. {TEST_PROJECT_PATH}/app/shop/controller/Goods.php, "
        "Order.php), 2-3 sample view files under "
        f"{TEST_PROJECT_PATH}/app/shop/view/, and skim "
        f"{TEST_PROJECT_PATH}/b2c_mall.sql — just enough to learn the "
        "conventions: how action methods look (public function), how views "
        "mark elements (id=/name=/lay-filter=), how CREATE TABLE is written, "
        "and how controllers reference DB tables (Db::name / model).\n"
        "2. WRITE A COLLECTOR SCRIPT: use write_file to create a Python "
        f"script at {TEST_PROJECT_PATH}/_atlas_collect.py that scans the "
        "whole project MECHANICALLY:\n"
        f"   - app/shop/controller/*.php → per entity: all public function "
        "names + exact line numbers (candidate actions); EXCLUDE infra "
        "controllers (Base*/Login/Index/Error/Upload/Config/System/H5/"
        "Ueditor/Upgrade/Verify/Export) and inherited/base methods.\n"
        f"   - app/shop/view/<entity>/*.html → element symbols "
        "(id=/name=/lay-filter= values) with file + line.\n"
        f"   - b2c_mall.sql → CREATE TABLE: table name, columns, primary key.\n"
        f"   - Write ONE JSON to {TEST_PROJECT_PATH}/_atlas_raw.json with "
        "structure {entity: {actions: [{name, line}], elements: [{name, "
        "page, line}], db_tables: [{table, pk, cols}]}}.\n"
        "3. RUN it: execute_command `python3 "
        f"{TEST_PROJECT_PATH}/_atlas_collect.py`, then inspect the JSON "
        "(spot-check a few entities, fix the script if extraction looks "
        "wrong, rerun until solid).\n"
        "4. create_plan with one step per entity found in the JSON "
        "(typically 35-45).\n"
        "5. For EACH entity: enrich the raw facts with your own semantics — "
        "kind (read/write), risk_tier (money for price/stock/balance/refund/"
        "status writes, data for reads, ui for page views), business_rule "
        "(one line, infer from method name + ThinkPHP CRUD conventions), "
        "touches_tables (from script output / naming conventions), "
        "set_fields for writes, aliases (English identifier + Chinese "
        "business term). Then call write_app_map ONCE with the complete "
        "five-layer payload. Citations: controller = app/shop/controller/"
        "<Entity>.php + line from the script output; page/line for elements "
        "from the script output. If validation rejects, fix and retry.\n"
        "6. After each successful write_app_map, call "
        "generate_macros_from_app_map with the returned id, then "
        "update_step_status.\n"
        "CRITICAL: The mission is complete ONLY when EVERY plan step is "
        "completed. When a worker run approaches its step budget, report "
        "progress and remaining entities explicitly so the next ticket "
        "continues coverage — do NOT finish early.\n"
        "Topic: Atlas Wide Survey"
    )

    references = []
    if skill:
        references.append(
            {
                "type": "skill",
                "id": str(skill.id),
                "metadata": {
                    "skill_id": skill.id,
                    "skill_name": skill.name,
                    "description": skill.description or "",
                },
            }
        )

    logger.info(f"[Test] Dispatching agent run (thread_id={thread_id})...")
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=TEST_PROJECT_ID,
        references=references,
        skip_message_persistence=True,
        metadata={"goal_prefix": "[Atlas Survey] "},
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    result.inputs.setdefault("metadata", {})
    result.inputs["metadata"]["user_id"] = "atlas-test-1"
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["long_horizon"] = True

    logger.info(f"[Test] Running agent (timeout={timeout}s)...")
    start = time.time()
    model = result.inputs.get("model")
    try:
        stats = await asyncio.wait_for(
            _run_until_plan_complete(thread_id, result.inputs, model),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"Agent timed out after {time.time() - start:.1f}s")

    logger.info(
        f"[Test] Agent completed in {time.time() - start:.1f}s "
        f"(HITL auto-approvals: {stats['hitl']}, continuation turns: {stats['turns']})"
    )
    return thread_id


async def _count_pending_plan_steps(thread_id: str) -> int:
    from sqlalchemy import func, select

    from app.infrastructure.database import session_scope
    from app.models.planning import Plan, PlanStep

    async with session_scope() as db:
        plan_id = (
            await db.execute(
                select(Plan.id)
                .where(Plan.thread_id == thread_id)
                .order_by(Plan.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if plan_id is None:
            return 0
        return (
            await db.execute(
                select(func.count())
                .select_from(PlanStep)
                .where(
                    PlanStep.plan_id == plan_id,
                    PlanStep.status.in_(["pending", "in_progress"]),
                )
            )
        ).scalar_one()


async def _run_until_plan_complete(
    thread_id: str, inputs: dict, model: str | None, max_turns: int = 10
) -> dict:
    """Drive the agent until the survey plan is fully completed.

    If the supervisor ends a turn with pending plan steps (e.g. it routed to
    chat to ask the user what to do), nudge it with a follow-up message —
    exactly what a real user would reply.
    """
    from app.core.engine.dispatch import dispatch_agent_run

    stats = {"hitl": 0, "turns": 0}
    counter = await _run_with_hitl_auto_approve(thread_id, inputs, model)
    stats["hitl"] += counter[0]

    for turn in range(max_turns):
        pending = await _count_pending_plan_steps(thread_id)
        if pending == 0:
            logger.info(
                f"[Test] Plan fully completed after {turn} continuation turn(s)"
            )
            return stats

        stats["turns"] += 1
        logger.info(
            f"[Test] {pending} plan steps still pending — "
            f"sending continuation nudge (turn {turn + 1}/{max_turns})"
        )
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=(
                f"继续执行勘测计划：还有 {pending} 个实体未完成。请按 AppMap "
                "Analysis SOP 逐实体 write_app_map + generate_macros_from_app_map，"
                "并 update_step_status，直到所有计划步骤 completed。"
                "所有工具调用必须使用绝对路径。不要停下来询问，直接继续执行。"
            ),
            project_id=TEST_PROJECT_ID,
            skip_message_persistence=True,
            metadata={"goal_prefix": "[Atlas Survey] "},
        )
        if result.status == "failed":
            raise RuntimeError(f"Continuation dispatch failed: {result.error}")
        result.inputs.setdefault("metadata", {})
        result.inputs["metadata"]["user_id"] = "atlas-test-1"
        result.inputs["metadata"]["skip_persistence"] = True
        result.inputs["metadata"]["long_horizon"] = True
        counter = await _run_with_hitl_auto_approve(thread_id, result.inputs, model)
        stats["hitl"] += counter[0]

    logger.warning(f"[Test] Reached max continuation turns ({max_turns})")
    return stats


async def _run_with_hitl_auto_approve(
    thread_id: str, inputs: dict, model: str | None, max_resumes: int = 80
) -> list[int]:
    """Run the agent; auto-approve path-authorization HITLs via the
    production /resume path (resume_graph_background), exactly like a user
    clicking Approve in the UI."""
    from langchain_core.messages import ToolMessage

    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.graph_runner import resume_graph_background
    from app.core.hitl.orchestrator import HITLOrchestrator, get_pending_hitl_call

    counter = [0]
    await run_agent_background(thread_id, inputs)

    for resume_round in range(max_resumes):
        pending = await get_pending_hitl_call(
            {"configurable": {"thread_id": thread_id, "model": model}}
        )
        if not pending:
            if resume_round:
                logger.info("[Test] No pending HITL — run finished")
            return counter

        logger.info(
            f"[Test] HITL #{resume_round + 1}: auto-approving "
            f"{pending['name']} {pending.get('args')}"
        )
        normalized = await HITLOrchestrator.handle_resume(
            thread_id, pending, "approved"
        )
        tool_msg = ToolMessage(tool_call_id=pending["id"], content=normalized)
        config = {
            "configurable": {
                "thread_id": thread_id,
                "model": model,
                "run_id": f"hitl-resume-{resume_round}-{int(time.time())}",
            },
            "metadata": {"project_id": TEST_PROJECT_ID},
        }
        await resume_graph_background(thread_id, {"messages": [tool_msg]}, config)
        counter[0] += 1

    logger.warning(f"[Test] Hit max HITL resumes ({max_resumes})")
    return counter


INFRA_CONTROLLERS = {
    "baseshop",
    "login",
    "index",
    "error",
    "upload",
    "config",
    "system",
    "h5",
    "ueditor",
    "upgrade",
    "verify",
    "export",
}


def _census_business_entities() -> list[str]:
    """Ground truth: business-entity controllers on disk."""
    controller_dir = os.path.join(TEST_PROJECT_PATH, "app/shop/controller")
    entities = []
    for fname in sorted(os.listdir(controller_dir)):
        if not fname.endswith(".php"):
            continue
        name = fname[:-4].lower()
        if name not in INFRA_CONTROLLERS:
            entities.append(name)
    return entities


async def _verify_results():
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.app_map import AppMap
    from app.models.macro import Macro

    async with session_scope() as db:
        maps = (
            (
                await db.execute(
                    select(AppMap).where(AppMap.project_id == TEST_PROJECT_ID)
                )
            )
            .scalars()
            .all()
        )
        macros = (
            (await db.execute(select(Macro).where(Macro.project_id == TEST_PROJECT_ID)))
            .scalars()
            .all()
        )

    print("\n" + "=" * 78)
    print(
        f"{'entity':<16} {'v':>3} {'actions':>8} {'elements':>9} {'macros':>7} {'status':>10}"
    )
    print("-" * 78)
    for m in sorted(maps, key=lambda x: (x.entity or "", x.map_version)):
        n = len([x for x in macros if x.app_map_id == m.id])
        print(
            f"{m.entity:<16} {m.map_version:>3} {len(m.actions or []):>8} "
            f"{len(m.elements or []):>9} {n:>7} {m.status:>10}"
        )
    print("-" * 78)
    active_maps = [m for m in maps if m.status == "active"]
    superseded = [m for m in maps if m.status == "superseded"]
    print(
        f"合计: {len(maps)} 张地图 ({len(active_maps)} active / "
        f"{len(superseded)} superseded), {len(macros)} 个宏候选"
    )

    census = _census_business_entities()
    covered = {m.entity.lower() for m in active_maps if m.entity}
    missing = [e for e in census if e not in covered]
    print(
        f"\n全量业务控制器: {len(census)} 个 | 已覆盖: {len(covered)} 个 "
        f"({len(covered) / len(census):.0%})"
    )
    if missing:
        print(f"未覆盖 ({len(missing)}): {', '.join(missing)}")

    for mc in macros:
        print(
            f"  宏 #{mc.id} {mc.name} [{mc.risk_tier}] "
            f"status={mc.status} confirm={mc.requires_confirmation}"
        )

    assert len(active_maps) >= 10, (
        f"Wide coverage failed: expected >= 10 active entity maps "
        f"(census={len(census)}), got {len(active_maps)}. Missing: {missing}"
    )
    assert len(macros) >= 1, f"Expected >= 1 macro candidate, got {len(macros)}"
    for m in active_maps:
        assert len(m.actions or []) >= 1, f"Map {m.entity} has no actions"

    logger.info("[Test] ✅ All assertions passed")
    return maps, macros


async def main():
    parser = argparse.ArgumentParser(description="Atlas Wide Survey Lifecycle Test")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT)
    parser.add_argument("--skip-clear", action="store_true")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip agent run; only verify current DB state",
    )
    args = parser.parse_args()

    if not os.path.isdir(TEST_PROJECT_PATH):
        logger.error(f"Project path does not exist: {TEST_PROJECT_PATH}")
        sys.exit(1)

    if args.verify_only:
        await _init_backend()
        try:
            await _verify_results()
            logger.info("✅ VERIFY-ONLY PASSED")
        except AssertionError as e:
            logger.error(f"❌ VERIFY-ONLY FAILED: {e}")
            sys.exit(1)
        finally:
            from app.infrastructure.database.resource_manager import (
                db_resource_manager,
            )

            await db_resource_manager.shutdown()
        return

    logger.info("=" * 60)
    logger.info("Atlas AppMap Wide Survey — Lifecycle Test")
    logger.info("=" * 60)
    logger.info(f"Project ID:   {TEST_PROJECT_ID}  (FIXED)")
    logger.info(f"Project Path: {TEST_PROJECT_PATH}  (FIXED)")

    await _init_backend()

    worker_proc = None
    try:
        if not args.skip_clear:
            await _clear_existing_maps()

        skill = await _ensure_skill()
        worker_proc = _start_worker()

        start = time.time()
        thread_id = await _run_survey_agent(skill, args.timeout)

        # Grace period for the worker to drain queued synthesis tasks
        logger.info("[Test] Waiting 20s for worker to drain queued tasks...")
        await asyncio.sleep(20)

        maps, macros = await _verify_results()

        logger.info("=" * 60)
        logger.info("✅ ATLAS SURVEY LIFECYCLE TEST PASSED")
        logger.info("=" * 60)
        logger.info(
            f"Thread ID: {thread_id}  Maps: {len(maps)}  "
            f"Macros: {len(macros)}  Time: {time.time() - start:.1f}s"
        )
    except AssertionError as e:
        logger.error(f"❌ TEST FAILED (assertion): {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ TEST FAILED (error): {e}")
        sys.exit(1)
    finally:
        if worker_proc is not None:
            logger.info("[Test] Stopping worker...")
            worker_proc.send_signal(signal.SIGTERM)
            try:
                worker_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker_proc.kill()
        from app.infrastructure.database.resource_manager import db_resource_manager

        await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
