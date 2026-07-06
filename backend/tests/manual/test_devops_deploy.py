#!/usr/bin/env python3
"""
EvoLoop DevOps — Deploy + Vault + HITL Integration Test

Tests real LLM agent behavior for deployment scenarios:
  1. Deploy with vault credentials — agent discovers credential and uses placeholder.
  2. Deploy without vault credentials — agent asks human via HITL, receives credential,
     and proceeds.

Safety:
  - Uses mock ssh/sshpass/rsync binaries injected into PATH so the deploy script never
    touches a real server. The command is executed against 127.0.0.1 but the SSH binaries
    are no-ops.
  - Real LLM (kimi-k2-thinking-turbo), no inference engine mocks.

Usage:
  cd evoloop/backend
  uv run python tests/manual/test_devops_deploy.py --case with_vault
  uv run python tests/manual/test_devops_deploy.py --case without_vault
  uv run python tests/manual/test_devops_deploy.py --case all
"""

import argparse
import asyncio
import logging
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("devops_deploy_test")

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
            "DEVOPS DEPLOY EXECUTION METRICS",
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

    from app.infrastructure.database import session_scope
    from app.models.learning import LearnedSkill

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(LearnedSkill.is_active.is_(True))
        result = await session.execute(stmt)
        skills = result.scalars().all()
        logger.info(f"[Test] {len(skills)} active skill(s) available")
        for s in skills:
            logger.info(f"  - {s.name} (id={s.id}, namespace={getattr(s, 'namespace', 'N/A')})")
        return skills


async def seed_vault_credentials(project_id: int):
    from app.infrastructure.config.vault import SecureVaultService

    SecureVaultService.add_credential(
        identifier="devops_test_ssh",
        type="ssh",
        payload={"password": "lifecycle_test_secret_456", "username": "deploy_user"},
        project_id=project_id,
        description="DevOps deploy test SSH credential",
    )
    logger.info(f"[Test] Seeded vault credential: devops_test_ssh (project_id={project_id})")


async def clear_vault_credentials(project_id: int):
    from app.infrastructure.config.vault import SecureVaultService

    SecureVaultService.delete_credential("devops_test_ssh", project_id=project_id)
    logger.info(f"[Test] Cleared vault credential devops_test_ssh for project_id={project_id}")


@contextmanager
def mock_ssh_binaries():
    """Create temporary mock ssh/sshpass/rsync binaries and prepend them to PATH."""
    tmpdir = tempfile.mkdtemp(prefix="mock_ssh_")
    mock_script = (
        "#!/bin/bash\n"
        'echo "[MOCK] $(basename "$0") called with args: $@"\n'
        "exit 0\n"
    )
    for name in ["ssh", "sshpass", "rsync"]:
        path = os.path.join(tmpdir, name)
        with open(path, "w") as f:
            f.write(mock_script)
        os.chmod(path, 0o755)
        logger.info(f"[Mock] Created {path}")

    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmpdir}:{original_path}"
    logger.info(f"[Mock] PATH prepended with {tmpdir}")
    try:
        yield tmpdir
    finally:
        os.environ["PATH"] = original_path
        shutil.rmtree(tmpdir)
        logger.info("[Mock] Cleaned up mock SSH binaries")


@contextmanager
def patch_subprocess_for_deploy(mock_ssh_dir: str):
    """
    Monkey-patch asyncio.create_subprocess_shell so that any command containing
    devops.sh --action deploy (or deploy.sh) runs with mock SSH binaries in PATH.
    """
    import asyncio
    original = asyncio.create_subprocess_shell

    async def _patched(cmd, *args, **kwargs):
        cmd_str = cmd if isinstance(cmd, str) else str(cmd)
        if "devops.sh --action deploy" in cmd_str or "deploy.sh" in cmd_str:
            if not cmd_str.startswith("export PATH="):
                cmd = f"export PATH={mock_ssh_dir}:$PATH && {cmd_str}"
                logger.info("[Mock] Intercepted deploy command, injecting mock PATH")
        return await original(cmd, *args, **kwargs)

    asyncio.create_subprocess_shell = _patched
    try:
        yield
    finally:
        asyncio.create_subprocess_shell = original


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
        f"5. If SSH credentials are needed, FIRST check the vault with list_vault_credentials.\n"
        f"6. If a matching credential exists, use placeholder format: {{{{vault.<id>.password}}}} or {{{{vault.<id>.username}}}}.\n"
        f"7. If no credential exists, ask the user via ask_human for host/user/password, then save it to the vault.\n"
    )


def _build_deploy_message(host: str = "127.0.0.1", customer: str = "customer_test", target: str = "frontend") -> str:
    return (
        f"Please deploy the {target} target for customer '{customer}' to host {host}.\n"
        f"First validate the configuration, then perform the deployment.\n"
        f"Use SSH credentials from the vault if available; otherwise ask me for them.\n"
        f"Report whether the deployment command was constructed and executed."
    )


async def run_agent_with_hitl(
    thread_id: str,
    inputs: dict,
    model: str,
    project_id: int = DEFAULT_PROJECT_ID,
    timeout: int = DEFAULT_TIMEOUT,
    hitl_answer_provider=None,
) -> ExecutionMetrics:
    from langchain_core.messages import ToolMessage

    from app.core.engine.background_agent import run_agent_background
    from app.core.globals import get_graph
    from app.core.hitl.orchestrator import HITLOrchestrator, get_pending_hitl_call

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

            if hitl_answer_provider:
                answer = hitl_answer_provider(pending)
            else:
                answer = "approved"

            logger.info(f"[Test] Auto-answering HITL with: {answer[:200]}")

            normalized = await HITLOrchestrator.handle_resume(
                thread_id, pending, answer
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


def _collect_all_text(messages: list) -> str:
    """Collect content, meta_data (full stdout), and tool_calls from messages."""
    parts = []
    for m in messages:
        for attr_name in ["content", "meta_data"]:
            val = getattr(m, attr_name, None)
            if val:
                parts.append(str(val))
        if getattr(m, "category", None) == "assistant_tool_call" and getattr(m, "tool_calls", None):
            parts.append(str(m.tool_calls))
    return " ".join(parts)


async def verify_deploy(
    thread_id: str,
    expected_secret: str | None = None,
    model: str = DEFAULT_MODEL,
) -> bool:
    from sqlalchemy import select

    from app.core.globals import get_graph
    from app.infrastructure.database import session_scope
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

    all_text = _collect_all_text(messages)

    # 1. check_config was run before deploy
    assert "check_config" in all_text.lower(), (
        "Configuration validation was not performed before deploy. "
        f"Sample: {all_text[:500]}"
    )
    logger.info("[Verify] ✅ check_config step confirmed")

    # 2. deploy command was constructed
    deploy_invoked = (
        "--action deploy" in all_text
        or ("deploy" in all_text.lower() and "devops.sh" in all_text)
    )
    assert deploy_invoked, (
        "Deploy command was never constructed. "
        f"Sample: {all_text[:500]}"
    )
    logger.info("[Verify] ✅ Deploy command invocation confirmed")

    # 3. Vault or HITL was consulted
    vault_consulted = "list_vault_credentials" in all_text or "request_secure_credential" in all_text
    hitl_used = "ask_human" in all_text or "ask_confirm" in all_text
    assert vault_consulted or hitl_used, (
        "Agent did not consult vault or ask user for credentials. "
        f"Sample: {all_text[:500]}"
    )
    logger.info(f"[Verify] ✅ Credential handling confirmed (vault={vault_consulted}, hitl={hitl_used})")

    # 4. If a secret was expected, verify it is NOT exposed in any message content
    if expected_secret:
        assert expected_secret not in all_text, (
            "SECURITY FAIL: raw secret found in message content/metadata/tool_calls. "
            f"Sample: {all_text[:500]}"
        )
        logger.info("[Verify] ✅ Raw secret not found in messages (censorship likely active)")

    logger.info("[Verify] ✅ deploy verification passed")
    return True


async def run_case(case: str, project_id: int = DEFAULT_PROJECT_ID, **kwargs):
    from app.core.context import thread_context_store
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.sub_schemas import BlackboardState
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )

    thread_id = f"devops-deploy-{case}-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, EVOLOOP_ROOT)

    system_instructions = _build_system_instructions()
    host = kwargs.get("host", "127.0.0.1")
    customer = kwargs.get("customer", "customer_test")
    target = kwargs.get("target", "frontend")
    message = _build_deploy_message(host=host, customer=customer, target=target)

    logger.info("=" * 60)
    logger.info(f"CASE: {case}")
    logger.info(f"Thread:   {thread_id}")
    logger.info(f"Mission:  {message[:200]}")
    logger.info("=" * 60)

    skills = await get_skills()
    devops_skill = next((s for s in skills if "devops" in s.name.lower()), None)

    if case == "with_vault":
        await seed_vault_credentials(project_id)
        expected_secret = "lifecycle_test_secret_456"
    else:
        await clear_vault_credentials(project_id)
        expected_secret = "hitl_provided_secret_789"

    model = kwargs.get("model", DEFAULT_MODEL)

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        model=model,
        goal_prefix=f"[DevOps deploy {case}] ",
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic=f"DevOps deploy {case}",
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

    def hitl_answer_provider(pending: dict) -> str:
        tool_name = pending.get("name", "unknown")
        args = pending.get("arguments", pending.get("args", {}))
        prompt_text = str(args.get("prompt", "")) if args else ""
        if tool_name == "ask_human":
            lowered = prompt_text.lower()
            if any(k in lowered for k in ["密码", "password", "凭证", "credential", "ssh", "密钥", "key", "user"]):
                # Provide credentials for the deploy (only when asked for credentials)
                return (
                    "Host: 127.0.0.1\n"
                    "User: deploy_user\n"
                    "Password: hitl_provided_secret_789\n"
                    "Port: 22"
                )
            # Confirmation / continuation question
            return "yes, continue"
        return "approved"

    with mock_ssh_binaries() as mock_ssh_dir:
        with patch_subprocess_for_deploy(mock_ssh_dir):
            metrics = await run_agent_with_hitl(
                thread_id=thread_id,
                inputs=result.inputs,
                model=model,
                project_id=project_id,
                timeout=kwargs.get("timeout", DEFAULT_TIMEOUT),
                hitl_answer_provider=hitl_answer_provider,
            )

    from sqlalchemy import func, select

    from app.infrastructure.database import session_scope
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

    await verify_deploy(thread_id, expected_secret=expected_secret, model=model)

    return metrics


async def main():
    parser = argparse.ArgumentParser(description="EvoLoop DevOps Deploy + Vault + HITL Test")
    parser.add_argument(
        "--case",
        choices=["with_vault", "without_vault", "all"],
        default="all",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Deploy target host")
    parser.add_argument("--customer", default="customer_test", help="Customer profile")
    parser.add_argument("--target", default="frontend", help="Deploy target")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--project-id", type=int, default=DEFAULT_PROJECT_ID, help="Project ID")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    model = args.model

    logger.info("=" * 60)
    logger.info("EvoLoop DevOps — Deploy + Vault + HITL Integration Test")
    logger.info("=" * 60)
    logger.info(f"EvoLoop Root: {EVOLOOP_ROOT}")
    logger.info(f"Model:        {model}")
    logger.info(f"Project ID:   {args.project_id}")
    logger.info(f"Case:         {args.case}")
    logger.info(f"Timeout:      {args.timeout}s")
    logger.info("")

    try:
        await init_backend(project_id=args.project_id)

        cases = [args.case] if args.case != "all" else ["with_vault", "without_vault"]
        results = {}

        for case in cases:
            try:
                metrics = await run_case(
                    case,
                    project_id=args.project_id,
                    host=args.host,
                    customer=args.customer,
                    target=args.target,
                    timeout=args.timeout,
                    model=model,
                )
                results[case] = ("PASSED", metrics)
                logger.info(f"\n{'='*60}")
                logger.info(f"✅ CASE '{case}' PASSED ({metrics.elapsed_seconds:.1f}s)")
                logger.info(f"{'='*60}\n")
            except Exception as e:
                results[case] = ("FAILED", str(e))
                logger.error(f"\n{'='*60}")
                logger.error(f"❌ CASE '{case}' FAILED: {e}")
                logger.error(f"{'='*60}\n")

        logger.info("\n" + "=" * 60)
        logger.info("FINAL RESULTS")
        logger.info("=" * 60)
        all_passed = True
        for case, (status, detail) in results.items():
            icon = "✅" if status == "PASSED" else "❌"
            elapsed = f" ({detail.elapsed_seconds:.1f}s)" if hasattr(detail, "elapsed_seconds") else ""
            logger.info(f"  {icon} {case}: {status}{elapsed}")
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
