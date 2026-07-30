#!/usr/bin/env python3
"""Macro Creation — Full Lifecycle Manual Test with Real LLM.

Runs the complete macro creation flywheel with a real Agent engine,
real local database, and real LLM via the EvoLoop platform.  The agent is
asked to perform a harmless desktop AppleScript action so that the trace
contains a replayable step and the session can create a macro.

Usage:
    .venv/bin/python tests/manual/test_macro_sedimentation_lifecycle.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

os.environ.setdefault("EMBEDDED_MODE", "True")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sqlalchemy import select

from app.core.events.base import system_bus
from app.core.execution.macro.event.subscribers import MacroSedimentationSubscriber
from app.infrastructure.database import session_scope
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models import AgentActivity, Macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("macro_creation_lifecycle")

TEST_TIMEOUT = 300


async def _login_and_store_token(
    username: str = "preterchan", password: str = "hellomylife"
) -> int:
    """Login via EvoCloud manager and store token in IdentityStore."""
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning("[Test] Initialization had some issues: %s", e)

    logger.info("[Test] Logging in via EvoCloud as %s...", username)
    login_res = await evocloud_manager.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    member_id = await identity_service.get_member_id(token)
    logger.info("[Test] Login successful. member_id=%s", member_id)
    return member_id


async def _init_backend() -> None:
    """Initialize the real database, agent graph, and LLM platform."""
    from app.infrastructure.config.service import SystemConfigService

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    logger.info("[Test] Database initialized.")

    logger.info("[Test] Initializing agent graph...")
    from app.core.globals import init_agent_graph

    init_agent_graph()
    logger.info("[Test] Agent graph ready.")

    logger.info("[Test] Configuring LLM platform...")
    SystemConfigService.set_value("LLM_CONFIG_TYPE", "platform")
    SystemConfigService.set_value("LLM_BASE_URL", "")
    SystemConfigService.set_value("LLM_API_KEY", "")

    from app.infrastructure.llm.platform_service import get_available_llm_models

    models = await get_available_llm_models("platform")
    logger.info("[Test] Available platform models: %s", models)
    if models:
        selected_model = models[0]["id"]
        for m in models:
            mid = m["id"]
            if (
                "kimi" in mid.lower()
                or "gpt-4o" in mid.lower()
                or "deepseek" in mid.lower()
            ):
                selected_model = mid
                break
        SystemConfigService.set_value("LLM_MODEL", selected_model)
        logger.info("[Test] Selected LLM_MODEL: %s", selected_model)
    else:
        SystemConfigService.set_value("LLM_MODEL", "gpt-4o")
        logger.warning("[Test] No platform models found, falling back to gpt-4o")


async def _run_agent(
    thread_id: str, member_id: int, project_id: int, timeout: int
) -> None:
    """Dispatch and run an agent that performs a desktop action."""
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )
    from app.infrastructure.config.service import SystemConfigService

    thread_context_store.set_working_directory(thread_id, os.getcwd())

    user_lang = SystemConfigService.get_language_preference()

    system_instructions = (
        "You are a desktop automation assistant. "
        f"Respond in {user_lang}. "
        "Your task is to run a harmless AppleScript snippet using the desktop_control tool "
        "with action='applescript' and a script that returns the current date. "
        "After running the script, report that the task is completed."
    )

    message = (
        "Run a harmless AppleScript using the desktop_control tool: "
        "action='applescript', script='return (current date) as string'. "
        "Then report success and stop."
    )

    logger.info("[Test] Dispatching agent run (thread_id=%s)...", thread_id)
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        skip_message_persistence=True,
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    ticket = ExecutionTicket(
        ticket_type="task",
        topic="desktop_automation",
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=system_instructions,
            tools=["desktop_control"],
        ),
        parameters=TicketParameters(),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs["metadata"]["user_id"] = f"test-user-{member_id}"

    logger.info("[Test] Running agent (timeout=%ds)...", timeout)
    start = time.time()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        raise RuntimeError(f"Agent timed out after {elapsed:.1f}s")

    elapsed = time.time() - start
    logger.info("[Test] Agent completed in %.1fs", elapsed)


async def _verify_results(thread_id: str) -> tuple[Macro, AgentActivity]:
    """Assert that the macro and activity records reflect a successful flywheel."""
    async with session_scope() as db:
        macro = (
            await db.execute(select(Macro).where(Macro.source_thread_id == thread_id))
        ).scalar_one_or_none()

    async with session_scope() as db:
        activity = await db.get(AgentActivity, thread_id)

    if activity is None:
        raise AssertionError(f"AgentActivity missing for thread {thread_id}")

    logger.info(
        "[Test] AgentActivity: final_outcome=%s eligible=%s summary=%s",
        activity.final_outcome,
        activity.macro_creation_eligible,
        activity.summary,
    )

    if activity.final_outcome.upper() != "COMPLETED":
        raise AssertionError(
            f"Expected COMPLETED, got {activity.final_outcome}. "
            f"Creation eligible={activity.macro_creation_eligible}."
        )
    if not activity.macro_creation_eligible:
        raise AssertionError(
            "Activity is not macro-creation-eligible. No replayable trace events found."
        )

    if macro is None:
        raise AssertionError(f"No macro was created for thread {thread_id}")

    assert macro.status == "pending_review", f"Unexpected macro status: {macro.status}"
    assert macro.is_active is False, "Macro should not be active yet"
    assert macro.source_thread_id == thread_id, (
        f"Wrong source_thread_id: {macro.source_thread_id}"
    )

    logger.info(
        "[Test] Macro verified: id=%d name=%s status=%s member_id=%d",
        macro.id,
        macro.name,
        macro.status,
        macro.member_id,
    )
    return macro, activity


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Macro Creation Full Lifecycle Manual Test with Real LLM"
    )
    parser.add_argument(
        "--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds"
    )
    args = parser.parse_args()

    thread_id = f"macro-creation-real-llm-{int(time.time())}"
    project_id = 1

    logger.info("=" * 60)
    logger.info("Macro Creation — Full Lifecycle Manual Test (Real LLM)")
    logger.info("=" * 60)
    logger.info("Thread ID: %s", thread_id)
    logger.info("Project ID: %d", project_id)
    logger.info("Timeout: %ds", args.timeout)
    logger.info("")

    try:
        await _init_backend()
        member_id = await _login_and_store_token()

        system_bus.clear()
        MacroSedimentationSubscriber()
        logger.info("[Test] Registered MacroSedimentationSubscriber")

        await _run_agent(thread_id, member_id, project_id, args.timeout)
        await _verify_results(thread_id)

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ MACRO CREATION LIFECYCLE TEST PASSED")
        logger.info("=" * 60)
        logger.info("Thread ID: %s", thread_id)

    except (AssertionError, RuntimeError) as e:
        logger.error("❌ TEST FAILED: %s", e)
        raise
    except Exception as e:
        logger.exception("❌ TEST FAILED: %s", e)
        raise
    finally:
        logger.info("[Test] Cleaning up resources...")
        await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
