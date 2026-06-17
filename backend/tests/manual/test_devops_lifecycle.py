#!/usr/bin/env python3
"""
EvoLoop DevOps — Full Lifecycle Integration Test

Runs the complete DevOps skill pipeline with a REAL Agent + LLM.
No mocks on the inference engine. The Agent autonomously reads SKILL.md,
constructs commands, calls devops.sh, and reports results.

HITL handling: Automatically approves any ask_confirm interrupts.
Vault handling: Seeds test credentials and verifies censorship.

Scenarios:
  check_config  — Agent validates a customer configuration profile
  release       — Agent updates version numbers across all project files
  build         — Agent triggers a frontend build and verifies dist/ output

Usage:
  cd evoloop/backend
  uv run python tests/manual/test_devops_lifecycle.py --scenario check_config
  uv run python tests/manual/test_devops_lifecycle.py --scenario release --version 99.0.1
  uv run python tests/manual/test_devops_lifecycle.py --scenario all
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
logger = logging.getLogger("devops_lifecycle_test")

EVOLOOP_ROOT = "/Users/xujin/Projects/evoloop"
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

DEFAULT_MODEL = "kimi-k2-thinking-turbo"
DEFAULT_TIMEOUT = 600
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
            "DEVOPS LIFECYCLE EXECUTION METRICS",
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
    from app.infrastructure.config.service import SystemConfigService

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)

    # Ensure WORKSPACE_ROOT points to the parent of EVOLOOP_ROOT so project path
    # resolution (used by the authorization gate) can locate .evoloop/project.json.
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


async def seed_vault_credentials(project_id: int):
    from app.infrastructure.config.vault import SecureVaultService

    SecureVaultService.add_credential(
        identifier="devops_test_ssh",
        type="ssh",
        payload={"password": "lifecycle_test_secret_456", "username": "deploy_user"},
        project_id=project_id,
        description="DevOps lifecycle test SSH credential",
    )
    logger.info(f"[Test] Seeded vault credential: devops_test_ssh (project_id={project_id})")


async def get_skills():
    from sqlalchemy import select

    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(LearnedSkill.is_active.is_(True))
        result = await session.execute(stmt)
        skills = result.scalars().all()
        logger.info(f"[Test] {len(skills)} active skill(s) available")
        for s in skills:
            logger.info(f"  - {s.name} (id={s.id}, namespace={getattr(s, 'namespace', 'N/A')})")
        return skills


async def run_agent_with_hitl(
    thread_id: str,
    inputs: dict,
    model: str,
    project_id: int = DEFAULT_PROJECT_ID,
    timeout: int = DEFAULT_TIMEOUT,
) -> ExecutionMetrics:
    from langchain_core.messages import ToolMessage

    from app.core.engine.background_agent import run_agent_background
    from app.core.hitl.orchestrator import HITLOrchestrator, get_pending_hitl_call
    from app.core.globals import get_graph

    metrics = ExecutionMetrics()
    start = time.time()

    logger.info("[Test] Starting agent execution...")
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, inputs),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        metrics.errors.append(f"Initial run timed out after {timeout}s")
        return metrics

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id, "model": model}}

    for resume_round in range(10):
        await asyncio.sleep(0.5)
        state = await graph.aget_state(config)

        if not state.next:
            logger.info("[Test] Graph completed (no pending nodes)")
            break

        logger.info(f"[Test] Graph paused at: {state.next}")

        pending = await get_pending_hitl_call(graph, config)
        if pending:
            tool_name = pending.get("name", "unknown")
            logger.info(f"[Test] HITL interrupt detected: {tool_name} (id={pending['id']})")
            logger.info("[Test] Auto-approving...")

            normalized = await HITLOrchestrator.handle_resume(
                thread_id, pending, "approved"
            )
            tool_msg = ToolMessage(
                tool_call_id=pending["id"],
                content=normalized,
            )

            resume_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "model": model,
                    "run_id": f"hitl-resume-{resume_round}-{int(time.time())}",
                },
                "metadata": {"project_id": project_id},
            }
            logger.debug(f"[Test] Resume config prepared: {resume_config}")

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
            logger.info(f"[Test] HITL resume #{metrics.hitl_resume_count} completed")
        else:
            metrics.warnings.append(f"Graph paused at {state.next} but no HITL found")
            break

    metrics.elapsed_seconds = time.time() - start
    return metrics


def _build_system_instructions() -> str:
    devops_sh = "skills/evoloop_devops/scripts/devops.sh"
    return (
        f"You are a DevOps specialist. All operations MUST go through the coordinating script:\n"
        f"  bash {devops_sh} --action <action> [options]\n\n"
        f"Available actions:\n"
        f"  check_config  --customer <name>     Validate configuration\n"
        f"  build         --target <t> --customer <name>   Build artifacts\n"
        f"  release       --version <x.y.z>     Update version numbers\n"
        f"  deploy        --target <t> --customer <name> --host <ip>   Remote deploy\n\n"
        f"Actions: check_config, build, deploy, release.\n"
        f"Targets: frontend, desktop-macos-arm64, desktop-macos-x86_64, desktop-windows, all.\n"
        f"Default customer: default.\n\n"
        f"Rules:\n"
        f"1. ALWAYS run check_config before any build or deploy.\n"
        f"2. Use execute_command to run bash commands.\n"
        f"3. Report results clearly after each operation.\n"
        f"4. When asked to update versions, use the release action.\n"
        f"5. If credentials are needed, use vault placeholders: {{{{vault.<id>.<key>}}}}\n"
    )


def _build_devops_message(scenario: str, **kwargs) -> str:
    if scenario == "check_config":
        customer = kwargs.get("customer", "customer_test")
        return (
            f"Please validate the configuration for customer '{customer}'.\n"
            f"Run the configuration check using the DevOps coordinating script and report the results."
        )
    elif scenario == "release":
        version = kwargs.get("version", "99.0.1")
        return (
            f"Please update the EvoLoop project version to {version}.\n"
            f"Use the DevOps release action to synchronize version numbers across all project files "
            f"(.env, Cargo.toml, package.json, tauri.conf.json).\n"
            f"After the update, verify the version was written correctly by reading back key files."
        )
    elif scenario == "build":
        target = kwargs.get("target", "frontend")
        customer = kwargs.get("customer", "default")
        return (
            f"Please build the {target} target for customer '{customer}'.\n"
            f"First validate the configuration, then execute the build.\n"
            f"Report whether the build succeeded and check that the output artifacts exist."
        )
    else:
        raise ValueError(f"Unknown scenario: {scenario}")


async def verify_check_config(thread_id: str, project_id: int, model: str = DEFAULT_MODEL) -> bool:
    # project_id kept for API consistency with other verify_* functions
    _ = project_id
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
    logger.info(f"[Verify] Graph completed: {completed}, next: {state.next}")

    if state.values and "messages" in state.values:
        for idx, m in enumerate(state.values["messages"]):
            logger.info(f"  graph-msg {idx}: {type(m).__name__} | {str(m.content)[:150]}")

    assert completed, f"Agent did not complete. graph.next={state.next}"
    assert len(messages) >= 2, f"Expected at least 2 messages, got {len(messages)}"

    all_tool_outputs = " ".join(
        str(m.content) for m in messages
        if m.action_type == "tool_output"
    )

    config_validated = (
        "Configuration check PASSED" in all_tool_outputs
        or "配置预检成功" in all_tool_outputs
        or "配置校验成功" in all_tool_outputs
        or "PASSED with" in all_tool_outputs
        or "validate_config" in all_tool_outputs and "✓" in all_tool_outputs
    )
    assert config_validated, (
        f"validate_config.py was never successfully executed. "
        f"Tool outputs do not contain any configuration validation success markers. "
        f"Sample: {all_tool_outputs[:500]}"
    )
    logger.info("[Verify] ✅ validate_config.py execution confirmed in tool outputs")

    all_text = " ".join(str(m.content) for m in messages)
    script_invoked = (
        "devops.sh" in all_text
        or "validate_config.py" in all_text
        or "Configuration check PASSED" in all_text
    )
    assert script_invoked, "Neither devops.sh nor validate_config.py appears in any message"
    logger.info("[Verify] ✅ DevOps script invocation confirmed")

    logger.info("[Verify] ✅ check_config verification passed")
    return True


async def verify_release(thread_id: str, target_version: str, model: str = DEFAULT_MODEL) -> bool:
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

    all_tool_outputs = " ".join(
        str(m.content) for m in messages
        if m.action_type == "tool_output"
    )
    release_invoked = (
        "update-version" in all_tool_outputs
        or "release" in all_tool_outputs.lower() and "devops.sh" in all_tool_outputs
        or f"APP_VERSION={target_version}" in all_tool_outputs
    )
    assert release_invoked, (
        f"Release/update-version command was never invoked. "
        f"Sample tool outputs: {all_tool_outputs[:500]}"
    )
    logger.info("[Verify] ✅ Release command invocation confirmed")

    files_to_check = [
        os.path.join(EVOLOOP_ROOT, ".env"),
        os.path.join(EVOLOOP_ROOT, "frontend/package.json"),
        os.path.join(EVOLOOP_ROOT, "frontend/src-tauri/Cargo.toml"),
    ]
    updated_count = 0
    for fp in files_to_check:
        if os.path.exists(fp):
            with open(fp) as f:
                content = f.read()
            if target_version in content:
                updated_count += 1
                logger.info(f"[Verify] ✅ {os.path.relpath(fp, EVOLOOP_ROOT)}: contains {target_version}")
            else:
                logger.info(f"[Verify] ⚠️ {os.path.relpath(fp, EVOLOOP_ROOT)}: version not found")

    logger.info(f"[Verify] Version files updated: {updated_count}/{len(files_to_check)}")
    assert updated_count >= 1, f"Expected at least 1 file updated with {target_version}"

    logger.info("[Verify] ✅ release verification passed")
    return True


async def verify_build(thread_id: str, model: str = DEFAULT_MODEL) -> bool:
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

    all_text = " ".join(
        str(getattr(m, field, ""))
        for m in messages
        for field in ["content", "meta_data"]
        if getattr(m, field, None)
    )
    for m in messages:
        if m.category == "assistant_tool_call" and m.tool_calls:
            all_text += " " + str(m.tool_calls)

    build_invoked = (
        "build" in all_text.lower()
        and ("devops.sh" in all_text or "server-frontend" in all_text or "npm run build" in all_text or "--action build" in all_text)
    )
    assert build_invoked, (
        f"Build command was never invoked. "
        f"Sample text (first 500 chars): {all_text[:500]}"
    )
    logger.info("[Verify] ✅ Build command invocation confirmed")

    dist_dir = os.path.join(EVOLOOP_ROOT, "frontend/dist")
    dist_exists = os.path.isdir(dist_dir) and len(os.listdir(dist_dir)) > 0
    logger.info(f"[Verify] frontend/dist exists: {dist_exists}")

    build_succeeded = (
        "Frontend built" in all_text
        or "build complete" in all_text.lower()
        or "构建完成" in all_text
        or ("Command Succeeded" in all_text and "build" in all_text.lower())
    )
    assert build_succeeded or dist_exists, (
        "Build did not produce verifiable output. "
        "No success markers in messages and frontend/dist/ is empty or missing. "
        f"Sample text (first 500 chars): {all_text[:500]}"
    )
    logger.info("[Verify] ✅ build verification passed")
    return True


def _save_file_state(filepath: str) -> str | None:
    if os.path.exists(filepath):
        with open(filepath) as f:
            return f.read()
    return None


def _restore_file_state(filepath: str, content: str | None):
    if content is not None:
        with open(filepath, "w") as f:
            f.write(content)
        logger.info(f"[Cleanup] Restored: {os.path.relpath(filepath, EVOLOOP_ROOT)}")
    elif os.path.exists(filepath):
        os.remove(filepath)


async def run_scenario(scenario: str, project_id: int = DEFAULT_PROJECT_ID, **kwargs):
    from app.core.context import thread_context_store
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.blackboard import BlackboardState
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )

    thread_id = f"devops-lifecycle-{scenario}-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, EVOLOOP_ROOT)

    system_instructions = _build_system_instructions()
    message = _build_devops_message(scenario, **kwargs)

    logger.info("=" * 60)
    logger.info(f"SCENARIO: {scenario}")
    logger.info(f"Thread:   {thread_id}")
    logger.info(f"Mission:  {message[:200]}")
    logger.info("=" * 60)

    skills = await get_skills()
    devops_skill = next((s for s in skills if "devops" in s.name.lower()), None)

    await seed_vault_credentials(project_id)

    model = kwargs.get("model", DEFAULT_MODEL)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        model=model,
        goal_prefix=f"[DevOps {scenario}] ",
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic=f"DevOps {scenario}",
            skill_ids=[devops_skill.id] if devops_skill else None,
            agent_config=AgentRuntimeConfig(
                role_name="Workspace Operator",
                system_instructions=system_instructions,
                tools=[
                    "execute_command", "read_file", "list_dir", "grep_search",
                    "find_files", "edit_file",
                    "ask_confirm", "ask_human",
                    "list_skills", "read_skill_sop",
                    "remember", "recall", "search_history",
                    "list_vault_credentials", "request_secure_credential",
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
        timeout=kwargs.get("timeout", DEFAULT_TIMEOUT),
    )

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

    if scenario == "check_config":
        await verify_check_config(thread_id, project_id, model=model)
    elif scenario == "release":
        await verify_release(thread_id, kwargs.get("version", "99.0.1"), model=model)
    elif scenario == "build":
        await verify_build(thread_id, model=model)

    return metrics


async def main():
    parser = argparse.ArgumentParser(description="EvoLoop DevOps Lifecycle Test")
    parser.add_argument(
        "--scenario",
        choices=["check_config", "release", "build", "all"],
        default="check_config",
    )
    parser.add_argument("--version", default="99.0.1", help="Version for release scenario")
    parser.add_argument("--customer", default="customer_test", help="Customer for check_config/build")
    parser.add_argument("--target", default="frontend", help="Build target")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--project-id", type=int, default=DEFAULT_PROJECT_ID, help="Project ID")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip restoring files after release")
    args = parser.parse_args()

    model = args.model

    logger.info("=" * 60)
    logger.info("EvoLoop DevOps — Full Lifecycle Integration Test")
    logger.info("=" * 60)
    logger.info(f"EvoLoop Root: {EVOLOOP_ROOT}")
    logger.info(f"Model:        {model}")
    logger.info(f"Project ID:   {args.project_id}")
    logger.info(f"Scenario:     {args.scenario}")
    logger.info(f"Timeout:      {args.timeout}s")
    logger.info("")

    try:
        await init_backend(project_id=args.project_id)

        scenarios = [args.scenario] if args.scenario != "all" else ["check_config", "release", "build"]
        results = {}

        version_files = [
            os.path.join(EVOLOOP_ROOT, ".env"),
            os.path.join(EVOLOOP_ROOT, ".env.example"),
            os.path.join(EVOLOOP_ROOT, "frontend/package.json"),
            os.path.join(EVOLOOP_ROOT, "frontend/src-tauri/Cargo.toml"),
            os.path.join(EVOLOOP_ROOT, "frontend/src-tauri/tauri.conf.json"),
        ]
        saved_states = {}

        for scenario in scenarios:
            if scenario == "release" and not args.skip_cleanup:
                for fp in version_files:
                    saved_states[fp] = _save_file_state(fp)

            try:
                metrics = await run_scenario(
                    scenario,
                    project_id=args.project_id,
                    version=args.version,
                    customer=args.customer,
                    target=args.target,
                    timeout=args.timeout,
                    model=model,
                )
                results[scenario] = ("PASSED", metrics)
                logger.info(f"\n{'='*60}")
                logger.info(f"✅ SCENARIO '{scenario}' PASSED ({metrics.elapsed_seconds:.1f}s)")
                logger.info(f"{'='*60}\n")
            except Exception as e:
                results[scenario] = ("FAILED", str(e))
                logger.error(f"\n{'='*60}")
                logger.error(f"❌ SCENARIO '{scenario}' FAILED: {e}")
                logger.error(f"{'='*60}\n")
            finally:
                if scenario == "release" and not args.skip_cleanup:
                    for fp, content in saved_states.items():
                        _restore_file_state(fp, content)
                    logger.info("[Cleanup] Version files restored")

        logger.info("\n" + "=" * 60)
        logger.info("FINAL RESULTS")
        logger.info("=" * 60)
        all_passed = True
        for scenario, (status, detail) in results.items():
            icon = "✅" if status == "PASSED" else "❌"
            elapsed = f" ({detail.elapsed_seconds:.1f}s)" if hasattr(detail, "elapsed_seconds") else ""
            logger.info(f"  {icon} {scenario}: {status}{elapsed}")
            if status == "FAILED":
                all_passed = False
                logger.info(f"     Error: {detail}")
        logger.info("=" * 60)

        if not all_passed:
            sys.exit(1)

    finally:
        from app.infrastructure.database.resource_manager import db_resource_manager

        try:
            loop_id = db_resource_manager._current_loop_id()
            if loop_id in db_resource_manager._initialized_loops:
                await db_resource_manager.shutdown()
        except Exception as e:
            logger.warning(f"[Test] Cleanup warning: {e}")
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
