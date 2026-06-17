#!/usr/bin/env python3
"""
EvoLoop DevOps — Negative Integration Test

Verifies that the Agent does not proceed with build/deploy when configuration
validation fails.

Usage:
  cd evoloop/backend
  uv run python tests/manual/test_devops_negative.py
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("devops_negative_test")

EVOLOOP_ROOT = "/Users/xujin/Projects/evoloop"
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

DEFAULT_MODEL = "kimi-k2-thinking-turbo"
DEFAULT_TIMEOUT = 300
DEFAULT_PROJECT_ID = 57


@dataclass
class ExecutionMetrics:
    elapsed_seconds: float = 0.0
    hitl_resume_count: int = 0
    total_messages: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_report(self) -> str:
        lines = [
            "",
            "=" * 60,
            "DEVOPS NEGATIVE EXECUTION METRICS",
            "=" * 60,
            f"  Total elapsed:       {self.elapsed_seconds:.1f}s",
            f"  HITL resumes:        {self.hitl_resume_count}",
            f"  Total messages:      {self.total_messages}",
            "",
            "--- Tool Usage ---",
        ]
        for tool, count in sorted(self.tool_calls.items(), key=lambda x: -x[1]):
            lines.append(f"  {tool:30s}: {count}")
        if self.errors:
            lines.append("\n--- Errors ---")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("\n--- Warnings ---")
            for w in self.warnings:
                lines.append(f"  - {w}")
        lines.append("=" * 60)
        return "\n".join(lines)


async def init_backend(project_id: int = DEFAULT_PROJECT_ID):
    from app.infrastructure.database.resource_manager import db_resource_manager

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)

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


async def get_skills():
    from sqlalchemy import select

    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(LearnedSkill.is_active.is_(True))
        result = await session.execute(stmt)
        return result.scalars().all()


async def run_agent_with_hitl(thread_id: str, inputs: dict, model: str, project_id: int = DEFAULT_PROJECT_ID, timeout: int = DEFAULT_TIMEOUT) -> ExecutionMetrics:
    from langchain_core.messages import ToolMessage

    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.hitl import HITLOrchestrator, get_pending_hitl_call
    from app.core.globals import get_graph

    metrics = ExecutionMetrics()
    start = time.time()

    try:
        await asyncio.wait_for(run_agent_background(thread_id, inputs), timeout=timeout)
    except asyncio.TimeoutError:
        metrics.errors.append(f"Initial run timed out after {timeout}s")
        return metrics

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id, "model": model}}

    for resume_round in range(5):
        await asyncio.sleep(0.5)
        state = await graph.aget_state(config)
        if not state.next:
            break

        pending = await get_pending_hitl_call(graph, config)
        if pending:
            normalized = await HITLOrchestrator.handle_resume(thread_id, pending, "approved")
            tool_msg = ToolMessage(tool_call_id=pending["id"], content=normalized)
            try:
                await asyncio.wait_for(
                    run_agent_background(thread_id, {
                        "messages": [tool_msg.model_dump()],
                        "project_id": project_id,
                        "model": model,
                        "hitl_resume_response": normalized,
                    }),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                metrics.errors.append(f"Resume round {resume_round} timed out")
                break
            metrics.hitl_resume_count += 1
        else:
            break

    metrics.elapsed_seconds = time.time() - start
    return metrics


def _build_system_instructions() -> str:
    devops_sh = "skills/evoloop_devops/scripts/devops.sh"
    return (
        f"You are a DevOps specialist. All operations MUST go through:\n"
        f"  bash {devops_sh} --action <action> [options]\n\n"
        f"Rules:\n"
        f"1. ALWAYS run check_config before any build or deploy.\n"
        f"2. If check_config fails, STOP and report the failure. Do NOT build or deploy.\n"
        f"3. Use execute_command to run bash commands.\n"
    )


def _collect_all_text(messages: list) -> str:
    parts = []
    for m in messages:
        for attr_name in ["content", "meta_data"]:
            val = getattr(m, attr_name, None)
            if val:
                parts.append(str(val))
        if getattr(m, "category", None) == "assistant_tool_call" and getattr(m, "tool_calls", None):
            parts.append(str(m.tool_calls))
    return " ".join(parts)


async def verify_config_failure_blocks_build(thread_id: str, model: str = DEFAULT_MODEL) -> bool:
    from sqlalchemy import select

    from app.core.globals import get_graph
    from app.infrastructure.database.sql.database import session_scope
    from app.models import Message

    async with session_scope() as session:
        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
        res = await session.execute(stmt)
        messages = res.scalars().all()

    logger.info(f"[Verify] {len(messages)} messages in thread")
    for m in messages:
        logger.info(f"  * {m.role.upper()} ({m.action_type}/{m.category}): {str(m.content)[:200]}")

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id, "model": model}}
    state = await graph.aget_state(config)
    completed = not state.next
    logger.info(f"[Verify] Graph completed: {completed}")
    assert completed, f"Agent did not complete. graph.next={state.next}"

    all_text = _collect_all_text(messages)

    # check_config was attempted
    assert "check_config" in all_text.lower(), (
        "Configuration validation was not attempted. "
        f"Sample: {all_text[:500]}"
    )
    logger.info("[Verify] ✅ check_config attempted")

    # Collect only execute_command tool outputs for config validation assertion
    tool_outputs_text = " ".join(
        str(getattr(m, attr_name, ""))
        for m in messages
        if m.action_type == "tool_output" and m.tool_name == "execute_command"
        for attr_name in ["content", "meta_data"]
        if getattr(m, attr_name, None)
    )

    # check_config did NOT succeed
    config_success = (
        "Configuration check PASSED" in tool_outputs_text
        or "配置校验成功" in tool_outputs_text
    )
    assert not config_success, (
        "Configuration validation unexpectedly succeeded for invalid customer. "
        f"Tool outputs: {tool_outputs_text[:500]}"
    )
    logger.info("[Verify] ✅ check_config did not report success")

    # No build/deploy execute_command was attempted
    command_tool_calls = " ".join(
        str(m.tool_calls)
        for m in messages
        if m.category == "assistant_tool_call" and m.tool_calls
    )
    build_or_deploy = (
        "--action build" in command_tool_calls
        or "--action deploy" in command_tool_calls
    )
    assert not build_or_deploy, (
        "Agent attempted build or deploy despite failed configuration check. "
        f"Command tool calls: {command_tool_calls[:500]}"
    )
    logger.info("[Verify] ✅ No build/deploy attempted after config failure")

    logger.info("[Verify] ✅ negative test verification passed")
    return True


async def run_negative_case(project_id: int = DEFAULT_PROJECT_ID, model: str = DEFAULT_MODEL, timeout: int = DEFAULT_TIMEOUT):
    from app.core.context import thread_context_store
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.blackboard import BlackboardState
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )

    thread_id = f"devops-negative-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, EVOLOOP_ROOT)

    customer = "customer_negative"
    message = (
        f"Please build the frontend target for customer '{customer}'.\n"
        f"First validate the configuration, then execute the build.\n"
        f"If configuration validation fails, report the failure and stop."
    )

    logger.info("=" * 60)
    logger.info("CASE: config_failure_blocks_build")
    logger.info(f"Thread:   {thread_id}")
    logger.info(f"Mission:  {message[:200]}")
    logger.info("=" * 60)

    # Prepare a customer profile that will fail validation
    customer = "customer_negative"
    profile_dir = os.path.join(EVOLOOP_ROOT, "deploy/profiles", customer)
    profile_file = os.path.join(profile_dir, f"{customer}.env")
    os.makedirs(profile_dir, exist_ok=True)
    with open(profile_file, "w") as f:
        f.write("# Intentionally invalid profile for negative test\n")
        f.write("ENVIRONMENT=local\n")
        f.write("# VITE_API_URL intentionally missing\n")
    logger.info(f"[Test] Created invalid profile: {profile_file}")

    skills = await get_skills()
    devops_skill = next((s for s in skills if "devops" in s.name.lower()), None)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        model=model,
        goal_prefix="[DevOps negative] ",
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="DevOps negative config failure",
            skill_ids=[devops_skill.id] if devops_skill else None,
            agent_config=AgentRuntimeConfig(
                role_name="Workspace Operator",
                system_instructions=_build_system_instructions(),
                tools=[
                    "execute_command", "read_file", "list_dir", "grep_search",
                    "find_files", "edit_file",
                    "ask_confirm", "ask_human",
                    "list_skills", "read_skill_sop",
                    "remember", "recall", "search_history",
                ],
            ),
            parameters=TicketParameters(),
        )
    )
    result.inputs["blackboard"] = blackboard.model_dump(mode="json")
    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["long_horizon"] = True

    metrics = await run_agent_with_hitl(
        thread_id=thread_id,
        inputs=result.inputs,
        model=model,
        project_id=project_id,
        timeout=timeout,
    )

    # Cleanup the invalid profile
    try:
        if os.path.exists(profile_file):
            os.remove(profile_file)
        if os.path.exists(profile_dir):
            os.rmdir(profile_dir)
        logger.info("[Test] Cleaned up invalid customer profile")
    except Exception as e:
        logger.warning(f"[Test] Failed to cleanup profile: {e}")

    from sqlalchemy import func, select

    from app.infrastructure.database.sql.database import session_scope
    from app.models import Message

    async with session_scope() as session:
        count_stmt = select(func.count()).select_from(Message).where(Message.thread_id == thread_id)
        count_res = await session.execute(count_stmt)
        metrics.total_messages = count_res.scalar() or 0

        stmt = select(Message).where(Message.thread_id == thread_id)
        res = await session.execute(stmt)
        for m in res.scalars().all():
            if m.tool_name:
                metrics.tool_calls[m.tool_name] = metrics.tool_calls.get(m.tool_name, 0) + 1

    logger.info(metrics.to_report())
    await verify_config_failure_blocks_build(thread_id, model=model)
    return metrics


async def main():
    parser = argparse.ArgumentParser(description="EvoLoop DevOps Negative Integration Test")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--project-id", type=int, default=DEFAULT_PROJECT_ID)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("EvoLoop DevOps — Negative Integration Test")
    logger.info("=" * 60)
    logger.info(f"Model:        {args.model}")
    logger.info(f"Project ID:   {args.project_id}")
    logger.info(f"Timeout:      {args.timeout}s")
    logger.info("")

    try:
        await init_backend(project_id=args.project_id)
        metrics = await run_negative_case(
            project_id=args.project_id,
            model=args.model,
            timeout=args.timeout,
        )
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ NEGATIVE TEST PASSED ({metrics.elapsed_seconds:.1f}s)")
        logger.info(f"{'='*60}\n")
    except Exception as e:
        logger.error(f"\n{'='*60}")
        logger.error(f"❌ NEGATIVE TEST FAILED: {e}")
        logger.error(f"{'='*60}\n")
        sys.exit(1)
    finally:
        from app.infrastructure.database.resource_manager import db_resource_manager
        if db_resource_manager._initialized:
            await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
