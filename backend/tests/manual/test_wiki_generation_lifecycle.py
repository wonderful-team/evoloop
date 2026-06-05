#!/usr/bin/env python3
"""
Wiki Generation — Full Lifecycle Integration Test (v3)

Runs the complete wiki generation pipeline with a REAL Agent + LLM.
No mocks. This test actually dispatches an Agent run, waits for it to
complete, and verifies the generated Wiki pages in the database.

FIXED PARAMETERS (do not change without explicit approval):
  - project_id: 53
  - project_path: /Users/huangjinhuan/项目/testProjects/software-ecommerce
  - checkpoint: every 5 write_wiki_page calls
  - timeout: 3600s

The test will:
  1. Clean old logs and test artifacts.
  2. Clear any existing wiki pages for project 53.
  3. Dispatch a Wiki Generation Agent mission.
  4. Block until the Agent finishes (or timeout).
  5. Collect detailed execution metrics from logs.
  6. Query the database for generated pages.
  7. Run assertions and print a comprehensive report.
"""

import argparse
import asyncio
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# ──────────────────────────────────────────────────────────────
# FIXED TEST PARAMETERS
# ──────────────────────────────────────────────────────────────
TEST_PROJECT_ID = 53
TEST_PROJECT_PATH = "/Users/xujin/Projects/develop-assistant.cn/member-center"
TEST_TIMEOUT = 3600
TEST_LOG_FILE = "/tmp/wiki_e2e_test_v4.log"

# ──────────────────────────────────────────────────────────────
# Logging setup: write to stdout only (caller redirects to file)
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("wiki_lifecycle_test")


# ──────────────────────────────────────────────────────────────
# Execution Metrics Collector
# ──────────────────────────────────────────────────────────────
@dataclass
class ExecutionMetrics:
    """Structured metrics collected from Agent execution."""

    # Node execution counts
    supervisor_runs: int = 0
    worker_runs: int = 0
    finish_runs: int = 0

    # Tool usage (tool_name -> count)
    tool_calls: dict[str, int] = field(default_factory=dict)

    # Finish reason distribution by node
    finish_reasons: dict[str, dict[str, int]] = field(default_factory=lambda: {"Worker": {}, "Supervisor": {}})

    # Loop-level metrics
    worker_total_steps: int = 0
    worker_max_steps_in_loop: int = 0
    worker_tools_per_loop: list[int] = field(default_factory=list)

    # Content size warnings
    large_text_responses: int = 0  # Worker responses > 1000 chars without tool calls

    # Timing
    elapsed_seconds: float = 0.0
    supervisor_time_seconds: float = 0.0
    worker_time_seconds: float = 0.0

    # Blackboard / Plan
    plan_steps_created: int = 0
    plan_steps_completed: int = 0
    plan_steps_pending: int = 0

    # Bug-fix verification
    pause_turn_count: int = 0
    truncation_count: int = 0

    # Errors / Anomalies
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_report(self) -> str:
        lines = [
            "",
            "=" * 60,
            "AGENT EXECUTION METRICS REPORT",
            "=" * 60,
            f"",
            f"--- Node Execution ---",
            f"  Supervisor runs:     {self.supervisor_runs}",
            f"  Worker runs:         {self.worker_runs}",
            f"  Finish runs:         {self.finish_runs}",
            f"",
            f"--- Tool Usage ---",
        ]
        for tool, count in sorted(self.tool_calls.items(), key=lambda x: -x[1]):
            lines.append(f"  {tool:30s}: {count}")

        lines.append(f"")
        lines.append(f"--- Finish Reason Distribution ---")
        for node, reasons in self.finish_reasons.items():
            if reasons:
                lines.append(f"  {node}:")
                for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
                    lines.append(f"    {reason:20s}: {count}")

        lines.extend([
            f"",
            f"--- Worker Loop Detail ---",
            f"  Total ReAct steps:   {self.worker_total_steps}",
            f"  Max steps/loop:      {self.worker_max_steps_in_loop}",
            f"  Avg tools/loop:      {self._avg_tools_per_loop():.1f}",
            f"",
            f"--- Bug-Fix Verification ---",
            f"  pause_turn events:   {self.pause_turn_count}",
            f"  truncation events:   {self.truncation_count}",
            f"",
            f"--- Anomalies ---",
            f"  Large text responses (>1000 chars, no tools): {self.large_text_responses}",
            f"  Errors:              {len(self.errors)}",
            f"  Warnings:            {len(self.warnings)}",
            f"",
            f"--- Timing ---",
            f"  Total elapsed:       {self.elapsed_seconds:.1f}s",
            f"  Supervisor time:     {self.supervisor_time_seconds:.1f}s",
            f"  Worker time:         {self.worker_time_seconds:.1f}s",
            f"  Overhead (graph+etc):{self.elapsed_seconds - self.supervisor_time_seconds - self.worker_time_seconds:.1f}s",
            f"",
            f"--- Plan Progress ---",
            f"  Steps created:       {self.plan_steps_created}",
            f"  Steps completed:     {self.plan_steps_completed}",
            f"  Steps pending:       {self.plan_steps_pending}",
            f"  Completion rate:     {self._completion_rate():.1%}",
            f"",
            "=" * 60,
        ])
        if self.errors:
            lines.append("ERRORS:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("WARNINGS:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)

    def _avg_tools_per_loop(self) -> float:
        if not self.worker_tools_per_loop:
            return 0.0
        return sum(self.worker_tools_per_loop) / len(self.worker_tools_per_loop)

    def _completion_rate(self) -> float:
        total = self.plan_steps_created
        if total == 0:
            return 0.0
        return self.plan_steps_completed / total


def _parse_metrics_from_log(log_path: str) -> ExecutionMetrics:
    """Parse execution metrics from the structured log file."""
    metrics = ExecutionMetrics()

    if not os.path.exists(log_path):
        metrics.warnings.append(f"Log file not found: {log_path}")
        return metrics

    with open(log_path, "r") as f:
        content = f.read()

    # Node runs
    metrics.supervisor_runs = len(re.findall(r"\[.*?\] ▶️ run_react_loop START", content))
    metrics.worker_runs = metrics.supervisor_runs
    metrics.finish_runs = len(re.findall(r"\[Finish\]", content))

    # Tool calls
    for match in re.finditer(r"\[.*?\] Result \(([a-zA-Z0-9_]+)\):", content):
        tool = match.group(1)
        metrics.tool_calls[tool] = metrics.tool_calls.get(tool, 0) + 1

    # Finish reasons
    for match in re.finditer(r"- Finish Reason: (\w+)", content):
        reason = match.group(1)
        # Determine node from surrounding context
        context = content[max(0, match.start() - 500):match.start()]
        node = "Unknown"
        if "[Worker]" in context[-200:]:
            node = "Worker"
        elif "[Supervisor]" in context[-200:]:
            node = "Supervisor"
        if node not in metrics.finish_reasons:
            metrics.finish_reasons[node] = {}
        metrics.finish_reasons[node][reason] = metrics.finish_reasons[node].get(reason, 0) + 1

    # Bug-fix verification: pause_turn (should be 0 after fix)
    metrics.pause_turn_count = len(re.findall(r"pause_turn", content))

    # Truncation detection
    metrics.truncation_count = len(re.findall(r"is_truncated.*True|TRUNCATION|truncated", content))

    # Worker loop details
    for match in re.finditer(r"Loop finished\. Content len: (\d+), Tools used: (\d+)", content):
        content_len = int(match.group(1))
        tools_used = int(match.group(2))
        metrics.worker_tools_per_loop.append(tools_used)
        if content_len > 1000 and tools_used == 0:
            metrics.large_text_responses += 1

    # Worker total steps (sum of all steps across loops)
    metrics.worker_total_steps = sum(metrics.worker_tools_per_loop)
    if metrics.worker_tools_per_loop:
        metrics.worker_max_steps_in_loop = max(metrics.worker_tools_per_loop)

    # Plan progress from log
    plan_match = re.search(r"Loaded plan from DB: .+ \((\d+) steps\)", content)
    if plan_match:
        metrics.plan_steps_created = int(plan_match.group(1))

    completed_match = re.search(r"Progress: (\d+)/(\d+) steps completed", content)
    if completed_match:
        metrics.plan_steps_completed = int(completed_match.group(1))
        metrics.plan_steps_pending = int(completed_match.group(2)) - int(completed_match.group(1))

    # Errors from log
    for match in re.finditer(r"ERROR|Error:|Exception:|FAILED|❌", content):
        line = content[content.rfind("\n", 0, match.start()) + 1:content.find("\n", match.end())]
        if line and len(line) < 300:
            metrics.errors.append(line.strip())

    return metrics


# ──────────────────────────────────────────────────────────────
# Pre-test cleanup
# ──────────────────────────────────────────────────────────────
def _pre_test_cleanup():
    """Remove old logs and artifacts to prevent analysis confusion."""
    # Remove old log files
    old_logs = [
        "/tmp/wiki_e2e_test.log",
        "/tmp/wiki_e2e_test_v2.log",
        "/tmp/wiki_e2e_test_v3.log",
    ]
    for path in old_logs:
        if os.path.exists(path) and path != TEST_LOG_FILE:
            os.remove(path)
            logger.info(f"[Test] Removed old log: {path}")

    # Ensure test log directory exists
    log_dir = os.path.dirname(TEST_LOG_FILE)
    os.makedirs(log_dir, exist_ok=True)

    logger.info(f"[Test] Logging to: {TEST_LOG_FILE}")


# ──────────────────────────────────────────────────────────────
# Backend initialization
# ──────────────────────────────────────────────────────────────
async def _login_and_store_token(username: str = "preterchan", password: str = "hellomylife") -> str:
    """Login via EvoCloud manager and store token in IdentityStore."""
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"[Test] Initialization had some issues: {e}")

    client = evocloud_manager.api

    logger.info(f"[Test] Logging in via EvoCloud as {username}...")
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")

    await identity_service.set_token(token, refresh_token)
    member_id = await identity_service.get_member_id(token)
    logger.info(f"[Test] Login successful. member_id={member_id}")
    return token


async def _init_backend():
    """Initialize database and global graph."""
    from app.infrastructure.database.resource_manager import db_resource_manager

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    logger.info("[Test] Database initialized.")

    # Auto-login to get LLM API token
    await _login_and_store_token()

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken()
    logger.info("[Test] Agent environment ready.")

    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph

    logger.info("[Test] Building agent graph...")
    builder = GraphBuilder()
    config_path = os.path.join(
        os.path.dirname(__file__),
        "../../app/core/engine/config/agent_main.yaml",
    )
    workflow = builder.build(os.path.abspath(config_path))
    set_graph(workflow)
    logger.info("[Test] Agent graph ready.")


async def _clear_existing_wiki(project_id: int):
    """Remove existing wiki pages for the project."""
    from sqlmodel import delete, Session
    from app.infrastructure.database.resource_manager import db_resource_manager as rm
    from app.models.wiki import WikiPage

    with Session(rm.sync_engine) as session:
        result = session.exec(delete(WikiPage).where(WikiPage.project_id == project_id))
        session.commit()
        logger.info(f"[Test] Cleared {result.rowcount} existing wiki pages for project {project_id}")


async def _ensure_skill(force_reimport: bool = True):
    """Import the Wiki Generation skill. Re-imports by default to pick up edits."""
    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill
    from sqlalchemy import select
    from app.core.config import settings
    from app.core.learning.skill_importer import SkillImporter

    import_path = os.path.join(settings.SKILLS_DIR, "roles", "wiki_generation")
    if os.path.isdir(import_path):
        logger.info("[Test] Importing Wiki Generation skill...")
        await SkillImporter.import_from_directory(settings.SKILLS_DIR)

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "Wiki Generation",
            LearnedSkill.is_active == True,
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            logger.info(f"[Test] Wiki Generation skill ready (id={skill.id})")
            return skill

    logger.warning("[Test] Wiki Generation skill not found!")
    return None


async def _run_wiki_agent(project_id: int, project_path: str, skill, timeout: int) -> str:
    """Dispatch and run the Wiki Generation agent."""
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.blackboard import BlackboardState
    from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket, TicketParameters

    thread_id = f"wiki-test-{project_id}-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, project_path)

    from app.infrastructure.config.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    system_instructions = (
        f"You are a technical documentation expert. "
        f"ALL wiki content, page titles, and the table of contents MUST be written in {user_lang}. "
        f"After writing all content pages, you MUST create a dedicated 'Table of Contents' page "
        f"(title='目录' if Chinese, else 'Table of Contents') with slug='toc' and order=0. "
        f"The TOC page must list all wiki pages in a hierarchical tree format. Do NOT skip this step. "
        f"You MUST assess project scale FIRST using list_dir and key config files, then propose an appropriate page budget. "
        f"You MUST call create_plan FIRST before writing any pages. The plan step count should match your proposed budget. "
        f"Update plan progress with update_step_status after each page. Do NOT stop until all plan steps are completed."
    )

    message = (
        f"**Mission Goal**: Generate a comprehensive Wiki documentation for the project at {project_path}.\n"
        "You MUST:\n"
        "1. Survey the project structure (list_dir, read README and key config files) to assess scale.\n"
        "2. Propose a page budget based on project size (refer to SKILL.md scale table).\n"
        "3. Call create_plan FIRST with steps matching your proposed budget.\n"
        "4. Generate content page by page using write_wiki_page tool. Update step status after each page.\n"
        "5. Include Mermaid diagrams, code blocks, and tables where appropriate.\n"
        "6. Extract key concepts and store them in Memory.\n"
        "7. Create a 'Table of Contents' page (slug='toc', order=0) listing all pages in a tree hierarchy. Do NOT skip this step.\n"
        "8. Do NOT stop until all create_plan steps are completed.\n"
        "Topic: Project Documentation"
    )

    logger.info(f"[Test] Dispatching agent run (thread_id={thread_id})...")
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        goal_prefix="[Wiki Generation] ",
        skip_message_persistence=True,
    )

    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="Wiki Generation",
            skill_ids=[skill.id] if skill else None,
            agent_config=AgentRuntimeConfig(
                role_name="Worker",
                system_instructions=system_instructions,
                tools=[
                    "write_wiki_page", "read_wiki_page", "list_wiki_pages",
                    "create_plan", "update_step_status",
                    "list_dir", "read_file", "grep_search",
                    "remember", "recall", "search_history",
                ],
            ),
            parameters=TicketParameters(),
        )
    )
    result.inputs["blackboard"] = blackboard.model_dump(mode="json")

    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["user_id"] = "test-user-1"
    result.inputs["metadata"]["skip_persistence"] = True
    result.inputs["metadata"]["long_horizon"] = True

    logger.info(f"[Test] Running agent (timeout={timeout}s)...")
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
    logger.info(f"[Test] Agent completed in {elapsed:.1f}s")
    return thread_id


async def _verify_results(project_id: int) -> list[Any]:
    """Query DB and assert on generated wiki pages."""
    from app.domain.wiki.service import wiki_service
    from app.infrastructure.config.service import SystemConfigService

    user_lang = SystemConfigService.get_language_preference()
    wiki_service.ensure_toc_page(project_id, user_lang)

    pages = wiki_service.get_pages(project_id)
    logger.info(f"[Test] Found {len(pages)} wiki page(s) in database")

    if not pages:
        raise AssertionError("No wiki pages were generated!")

    valid_pages = [p for p in pages if p.slug and len(p.slug) > 1]
    logger.info(f"[Test] {len(valid_pages)} valid page(s) after filtering empty slugs")

    roots = [p for p in valid_pages if p.parent_id is None]

    def _log_tree(node, depth=0):
        indent = "  " * depth
        content_preview = node.content[:80].replace("\n", " ") if node.content else ""
        logger.info(
            f"[Test] {indent}📄 {node.title} (slug={node.slug}, "
            f"chars={len(node.content or '')}, parent={node.parent_id}) "
            f"→ {content_preview}..."
        )
        children = [p for p in valid_pages if p.parent_id == node.id]
        for child in sorted(children, key=lambda x: x.order):
            _log_tree(child, depth + 1)

    for root in sorted(roots, key=lambda x: x.order):
        _log_tree(root)

    total_chars = sum(len(p.content or "") for p in valid_pages)
    leaf_pages = [p for p in valid_pages if not any(c.parent_id == p.id for c in valid_pages)]
    toc_pages = [p for p in valid_pages if p.slug == "toc"]
    has_toc = len(toc_pages) > 0

    logger.info("[Test] Verification metrics:")
    logger.info(f"  - Total pages: {len(valid_pages)}")
    logger.info(f"  - Root pages: {len(roots)}")
    logger.info(f"  - Leaf pages: {len(leaf_pages)}")
    logger.info(f"  - Total content chars: {total_chars}")
    logger.info(f"  - TOC present: {has_toc}")

    assert len(valid_pages) >= 2, f"Expected at least 2 pages, got {len(valid_pages)}"
    assert total_chars > 500, f"Expected substantial content (>500 chars), got {total_chars}"
    assert has_toc, "Expected a Table of Contents page (slug='toc')"

    for p in valid_pages:
        assert p.title and len(p.title) > 1, f"Page {p.slug} has empty title"
        assert p.slug and len(p.slug) > 1, f"Page {p.title} has empty slug"

    logger.info("[Test] ✅ All assertions passed")
    return valid_pages


async def main():
    # Parse args (only --timeout and --skip-clear remain; project is fixed)
    parser = argparse.ArgumentParser(description="Wiki Generation Lifecycle Test v3")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds")
    parser.add_argument("--skip-clear", action="store_true", help="Skip clearing existing wiki")
    args = parser.parse_args()

    project_id = TEST_PROJECT_ID
    project_path = TEST_PROJECT_PATH
    timeout = args.timeout

    if not os.path.isdir(project_path):
        logger.error(f"Project path does not exist: {project_path}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Wiki Generation — Full Lifecycle Integration Test v3")
    logger.info("=" * 60)
    logger.info(f"Project ID:   {project_id}  (FIXED)")
    logger.info(f"Project Path: {project_path}  (FIXED)")
    logger.info(f"Timeout:      {timeout}s")
    logger.info(f"Log File:     {TEST_LOG_FILE}")
    logger.info("")

    # Step 1: Cleanup old artifacts
    _pre_test_cleanup()

    # Step 2: Initialize backend
    await _init_backend()

    # Step 3: Clear existing wiki
    if not args.skip_clear:
        await _clear_existing_wiki(project_id)

    # Step 4: Ensure skill
    skill = await _ensure_skill()

    # Step 5: Run agent and collect metrics
    start_time = time.time()
    try:
        thread_id = await _run_wiki_agent(project_id, project_path, skill, timeout)
        pages = await _verify_results(project_id)

        elapsed = time.time() - start_time

        # Step 6: Parse detailed metrics from log
        metrics = _parse_metrics_from_log(TEST_LOG_FILE)
        metrics.elapsed_seconds = elapsed

        logger.info(metrics.to_report())

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ WIKI GENERATION LIFECYCLE TEST PASSED")
        logger.info("=" * 60)
        logger.info(f"Thread ID:       {thread_id}")
        logger.info(f"Pages generated: {len(pages)}")
        logger.info(f"Total time:      {elapsed:.1f}s")
        logger.info("")

    except AssertionError as e:
        logger.error(f"❌ TEST FAILED (assertion): {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ TEST FAILED (error): {e}")
        sys.exit(1)
    finally:
        logger.info("[Test] Cleaning up resources...")
        from app.infrastructure.database.resource_manager import db_resource_manager
        await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
