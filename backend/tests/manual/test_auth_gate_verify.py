#!/usr/bin/env python3
"""Focused verification of the authorization gate on sensitive file reads."""

import argparse
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("auth_gate_verify")

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
EVOLOOP_ROOT = "/Users/xujin/Projects/evoloop"
DEFAULT_PROJECT_ID = 57
DEFAULT_MODEL = "kimi-k2-thinking-turbo"


async def init_backend(project_id: int):
    from app.infrastructure.config.service import SystemConfigService
    from app.infrastructure.database.resource_manager import db_resource_manager

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)

    workspace_root = os.path.dirname(EVOLOOP_ROOT)
    current_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not current_root:
        SystemConfigService.set_value(
            "WORKSPACE_ROOT",
            workspace_root,
            description="Workspace root for local project discovery",
        )
        logger.info(f"[Test] Set WORKSPACE_ROOT={workspace_root}")

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken(project_id=project_id)

    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph

    logger.info("[Test] Building agent graph...")
    builder = GraphBuilder()
    config_path = os.path.join(BACKEND_ROOT, "app/core/engine/config/agent_main.yaml")
    workflow = builder.build(
        os.path.abspath(config_path),
        checkpointer=db_resource_manager.checkpointer,
    )
    set_graph(workflow)
    logger.info("[Test] Agent graph ready.")


async def run_read_sensitive_file(thread_id: str, project_id: int, model: str):
    from app.core.engine.background_agent import run_agent_background
    from app.core.globals import get_graph
    from app.core.hitl.authorization import AuthorizationService
    from app.core.hitl.orchestrator import get_pending_hitl_call
    from app.core.project.utils import get_project_path

    graph = get_graph()
    target_path = "/Users/xujin/Projects/evoloop/deploy/profiles/customer_test/customer_test.env"

    # Revoke any previously persisted grant so this run exercises the gate.
    service = AuthorizationService(project_id=project_id)
    await service.revoke_permission(target_path, "read")
    try:
        project_path = await get_project_path(project_id)
        rel_path = os.path.relpath(target_path, project_path)
        if not rel_path.startswith(".."):
            await service.revoke_permission(rel_path, "read")
    except Exception:
        pass

    inputs = {
        "messages": [{"role": "user", "content": f"Read the file {target_path} and tell me its contents."}],
        "project_id": project_id,
        "model": model,
    }
    config = {"configurable": {"thread_id": thread_id, "model": model}}

    logger.info("[Test] Starting agent...")
    try:
        await asyncio.wait_for(run_agent_background(thread_id, inputs), timeout=120)
    except asyncio.TimeoutError:
        logger.error("[Test] Initial run timed out")
        return False

    hitl_count = 0
    for _resume_round in range(5):
        await asyncio.sleep(0.5)
        state = await graph.aget_state(config)
        if not state.next:
            logger.info("[Test] Graph completed")
            break

        pending = await get_pending_hitl_call(graph, config)
        if not pending:
            logger.warning(f"[Test] Graph paused at {state.next} but no HITL found")
            break

        tool_name = pending.get("name", "unknown")
        logger.info(f"[Test] HITL interrupt: {tool_name} ({pending['id']})")

        try:
            await asyncio.wait_for(
                run_agent_background(thread_id, {
                    "project_id": project_id,
                    "model": model,
                    "hitl_resume_response": "approved",
                }),
                timeout=120,
            )
        except asyncio.TimeoutError:
            logger.error("[Test] Resume timed out")
            return False
        hitl_count += 1
        logger.info(f"[Test] HITL resume #{hitl_count} completed")

    logger.info(f"[Test] Total HITL resumes: {hitl_count}")
    return hitl_count > 0


async def main():
    parser = argparse.ArgumentParser(description="Verify authorization gate triggers HITL for sensitive file reads")
    parser.add_argument("--project-id", type=int, default=DEFAULT_PROJECT_ID)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    args = parser.parse_args()

    await init_backend(args.project_id)

    thread_id = f"auth-gate-verify-{int(time.time())}"
    triggered = await run_read_sensitive_file(thread_id, args.project_id, args.model)

    from app.infrastructure.database.resource_manager import db_resource_manager
    try:
        loop_id = db_resource_manager._current_loop_id()
        if loop_id in db_resource_manager._initialized_loops:
            await db_resource_manager.shutdown()
    except Exception as e:
        logger.warning(f"[Test] Cleanup warning: {e}")

    if triggered:
        logger.info("✅ Authorization gate triggered HITL as expected")
        sys.exit(0)
    else:
        logger.error("❌ Authorization gate did NOT trigger HITL")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
