#!/usr/bin/env python3
"""Macro Sedimentation — Big Workflow (10+ steps) Manual Test with Real LLM.

Runs the complete macro sedimentation flywheel with a real Agent engine and
real LLM.  The agent is asked to collect 10 pieces of macOS system information
via separate desktop_control AppleScript calls, so the resulting macro should
contain at least 10 deterministic steps.

Usage:
    .venv/bin/python tests/manual/test_macro_sedimentation_big_workflow.py
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
from app.core.execution.macro.schemas import MacroScript
from app.infrastructure.database import session_scope
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models import AgentActivity, Macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("macro_sedimentation_big_workflow")

TEST_TIMEOUT = 300
MIN_STEPS = 10

APPLESCRIPT_TASKS = [
    "return (current date) as string",
    "return time string of (current date)",
    "return short user name of (system info)",
    "return computer name of (system info)",
    "return system version of (system info)",
    "return output volume of (get volume settings) as string",
    "return (path to desktop) as string",
    "return (do shell script \"uptime\")",
    "return (do shell script \"whoami\")",
    "return (do shell script \"hostname\")",
]


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
    """Dispatch and run an agent that performs a multi-step desktop action."""
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

    script_list = "\n".join(
        f"{i + 1}. {script}" for i, script in enumerate(APPLESCRIPT_TASKS)
    )

    system_instructions = (
        "You are a desktop automation assistant. "
        f"Respond in {user_lang}. "
        "Your task is to collect 10 pieces of macOS system information. "
        "You MUST call the desktop_control tool EXACTLY 10 times, once for each "
        "AppleScript in the list below. Each call must use a DIFFERENT script; "
        "DO NOT call the same script twice. DO NOT combine multiple scripts into a "
        "single tool call. DO NOT add extra calls. After the 10th call, summarize "
        "the collected information as a Markdown list and report that the task is completed."
    )

    message = (
        "Collect exactly 10 pieces of macOS system information using desktop_control with "
        "action='applescript'. Make exactly 10 separate tool calls, each using a "
        "DIFFERENT script from the numbered list below. Do not repeat any script; do not "
        "combine scripts into one call.\n\n"
        f"{script_list}\n\n"
        "After the 10th and final call, summarize the results as a Markdown list and stop."
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
        activity.sedimentation_eligible,
        activity.summary,
    )

    if activity.final_outcome.upper() != "COMPLETED":
        raise AssertionError(
            f"Expected COMPLETED, got {activity.final_outcome}. "
            f"Sedimentation eligible={activity.sedimentation_eligible}."
        )
    if not activity.sedimentation_eligible:
        raise AssertionError(
            "Activity is not sedimentation-eligible. No replayable trace events found."
        )

    if macro is None:
        raise AssertionError(f"No macro was created for thread {thread_id}")

    assert macro.status == "pending_review", f"Unexpected macro status: {macro.status}"
    assert macro.is_active is False, "Macro should not be active yet"
    assert macro.source_thread_id == thread_id, (
        f"Wrong source_thread_id: {macro.source_thread_id}"
    )

    macro_script = MacroScript.from_yaml(macro.macro_script)
    step_count = len(macro_script.steps)
    scripts = [s.payload.get("script") for s in macro_script.steps]
    unique_scripts = set(scripts)
    logger.info("[Test] Compiled macro step count: %d", step_count)
    logger.info("[Test] Unique scripts in macro: %d", len(unique_scripts))
    if step_count < MIN_STEPS:
        raise AssertionError(
            f"Expected macro with at least {MIN_STEPS} steps, got {step_count}. "
            "The agent likely combined multiple AppleScript calls into one tool call."
        )
    if len(unique_scripts) < MIN_STEPS:
        duplicates = [s for s in scripts if scripts.count(s) > 1]
        raise AssertionError(
            f"Expected at least {MIN_STEPS} unique scripts, got {len(unique_scripts)}. "
            f"Duplicates found: {duplicates}."
        )
    if step_count != len(unique_scripts):
        logger.warning(
            "[Test] Agent produced %d total steps but only %d unique scripts; "
            "some scripts were repeated.",
            step_count,
            len(unique_scripts),
        )

    logger.info(
        "[Test] Macro verified: id=%d name=%s step_count=%d status=%s member_id=%d",
        macro.id,
        macro.name,
        step_count,
        macro.status,
        macro.member_id,
    )
    return macro, activity


async def main() -> None:
    global MIN_STEPS

    parser = argparse.ArgumentParser(
        description="Macro Sedimentation Big Workflow Manual Test with Real LLM"
    )
    parser.add_argument(
        "--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds"
    )
    parser.add_argument(
        "--min-steps", type=int, default=MIN_STEPS, help="Minimum expected macro steps"
    )
    args = parser.parse_args()

    MIN_STEPS = args.min_steps

    thread_id = f"macro-sedimentation-big-workflow-{int(time.time())}"
    project_id = 1

    logger.info("=" * 60)
    logger.info("Macro Sedimentation — Big Workflow Manual Test (Real LLM)")
    logger.info("=" * 60)
    logger.info("Thread ID: %s", thread_id)
    logger.info("Project ID: %d", project_id)
    logger.info("Timeout: %ds", args.timeout)
    logger.info("Minimum expected steps: %d", MIN_STEPS)
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
        logger.info("✅ MACRO SEDIMENTATION BIG WORKFLOW TEST PASSED")
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
