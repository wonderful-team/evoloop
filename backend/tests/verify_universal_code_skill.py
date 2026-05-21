#!/usr/bin/env python3
"""
Universal Code Development — Full Lifecycle Integration Test (Full-Stack Benchmark)

Runs the code development pipeline with a REAL Agent + LLM.
This test gives the Agent a massive, cross-stack architectural mandate:
building both the frontend UI and backend API for the PTE mock exam system.

FIXED PARAMETERS:
  - project_id: 99
  - project_path: /Users/huangjinhuan/项目/testProjects/software-ecommerce
  - timeout: 3600s (1 hour)
"""

import argparse
import asyncio
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ──────────────────────────────────────────────────────────────
# FIXED TEST PARAMETERS
# ──────────────────────────────────────────────────────────────
TEST_PROJECT_ID = 99
TEST_PROJECT_PATH = "/Users/huangjinhuan/项目/testProjects/software-ecommerce"
TEST_TIMEOUT = 10800
TEST_LOG_FILE = os.path.join(os.path.dirname(__file__), "code_dev_e2e_test.log")

# ──────────────────────────────────────────────────────────────
# Logging setup: write to stdout only (caller redirects to file)
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("code_dev_test")


# ──────────────────────────────────────────────────────────────
# Execution Metrics Collector
# ──────────────────────────────────────────────────────────────
@dataclass
class ExecutionMetrics:
    """Structured metrics collected from Agent execution."""
    supervisor_runs: int = 0
    worker_runs: int = 0
    finish_runs: int = 0
    tool_calls: dict[str, int] = field(default_factory=dict)
    finish_reasons: dict[str, dict[str, int]] = field(default_factory=lambda: {"Worker": {}, "Supervisor": {}})
    worker_total_steps: int = 0
    worker_max_steps_in_loop: int = 0
    worker_tools_per_loop: list[int] = field(default_factory=list)
    large_text_responses: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_report(self) -> str:
        lines = [
            "",
            "=" * 60,
            "AGENT EXECUTION METRICS REPORT (FULL-STACK BENCHMARK)",
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

        lines.extend([
            f"",
            f"--- Finish Reason Distribution ---"
        ])
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
            f"--- Anomalies ---",
            f"  Large text responses (>1000 chars, no tools): {self.large_text_responses}",
            f"  Errors:              {len(self.errors)}",
            f"  Warnings:            {len(self.warnings)}",
            f"",
            f"--- Timing ---",
            f"  Total elapsed:       {self.elapsed_seconds:.1f}s",
            f"",
            "=" * 60,
        ])
        return "\n".join(lines)

    def _avg_tools_per_loop(self) -> float:
        if not self.worker_tools_per_loop:
            return 0.0
        return sum(self.worker_tools_per_loop) / len(self.worker_tools_per_loop)


def _parse_metrics_from_log(log_path: str) -> ExecutionMetrics:
    """Parse execution metrics from the structured log file."""
    metrics = ExecutionMetrics()

    if not os.path.exists(log_path):
        metrics.warnings.append(f"Log file not found: {log_path}")
        return metrics

    with open(log_path, "r") as f:
        content = f.read()

    metrics.supervisor_runs = len(re.findall(r"\[Supervisor\] .+ run_react_loop START", content))
    metrics.worker_runs = len(re.findall(r"\[Worker\] .+ run_react_loop START", content))
    metrics.finish_runs = len(re.findall(r"\[Finish\] .+ run_react_loop START", content))

    for match in re.finditer(r"🛠️ Call: ([a-z_]+)", content):
        tool = match.group(1)
        metrics.tool_calls[tool] = metrics.tool_calls.get(tool, 0) + 1

    for match in re.finditer(r"- Finish Reason: (\w+)", content):
        reason = match.group(1)
        context = content[max(0, match.start() - 500):match.start()]
        node = "Unknown"
        if "[Worker]" in context[-200:]:
            node = "Worker"
        elif "[Supervisor]" in context[-200:]:
            node = "Supervisor"
        if node not in metrics.finish_reasons:
            metrics.finish_reasons[node] = {}
        metrics.finish_reasons[node][reason] = metrics.finish_reasons[node].get(reason, 0) + 1

    for match in re.finditer(r"Loop finished\. Content len: (\d+), Tools used: (\d+)", content):
        content_len = int(match.group(1))
        tools_used = int(match.group(2))
        metrics.worker_tools_per_loop.append(tools_used)
        if content_len > 1000 and tools_used == 0:
            metrics.large_text_responses += 1

    metrics.worker_total_steps = sum(metrics.worker_tools_per_loop)
    if metrics.worker_tools_per_loop:
        metrics.worker_max_steps_in_loop = max(metrics.worker_tools_per_loop)

    for match in re.finditer(r"ERROR|Error:|Exception:|FAILED|❌", content):
        line = content[content.rfind("\n", 0, match.start()) + 1:content.find("\n", match.end())]
        if line and len(line) < 300:
            metrics.errors.append(line.strip())

    return metrics


def _pre_test_cleanup():
    try:
        os.makedirs(os.path.dirname(TEST_LOG_FILE), exist_ok=True)
    except Exception:
        pass
    
    if os.path.exists(TEST_LOG_FILE):
        os.remove(TEST_LOG_FILE)
        logger.info(f"[Test] Removed old log: {TEST_LOG_FILE}")


# ──────────────────────────────────────────────────────────────
# Backend initialization
# ──────────────────────────────────────────────────────────────
async def _login_and_store_token(username: str = "preterchan", password: str = "hellomylife") -> str:
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"[Test] Initialization had some issues: {e}")

    client = evocloud_manager.api
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    logger.info("[Test] Login successful.")
    return token

async def _init_backend():
    from app.infrastructure.database.resource_manager import db_resource_manager
    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    
    await _login_and_store_token()

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken()

    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    workflow = builder.build(os.path.abspath(config_path))
    set_graph(workflow)
    logger.info("[Test] Agent graph ready.")


async def _ensure_skill():
    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill
    from sqlalchemy import select
    from app.core.config import settings
    from app.core.learning.skill_importer import SkillImporter

    # We import all roles, it will naturally pick up universal_code_development
    import_path = os.path.join(settings.SKILLS_DIR, "roles")
    if os.path.isdir(import_path):
        logger.info("[Test] Importing skills...")
        await SkillImporter.import_from_directory(settings.SKILLS_DIR)

    async with session_scope() as session:
        stmt = select(LearnedSkill).where(
            LearnedSkill.name == "universal_code_development",
            LearnedSkill.is_active == True,
        )
        result = await session.execute(stmt)
        skill = result.scalar_one_or_none()
        if skill:
            logger.info(f"[Test] universal_code_development skill ready (id={skill.id})")
            return skill

    logger.warning("[Test] universal_code_development skill not found!")
    return None


async def _run_code_agent(project_id: int, project_path: str, skill, timeout: int) -> str:
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.blackboard import BlackboardState
    from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket, TicketParameters

    thread_id = f"code-dev-fullstack-{int(time.time())}"
    thread_context_store.set_working_directory(thread_id, project_path)

    system_instructions = (
        "You are a Staff-level autonomous software engineer executing universal code development. "
        "Strictly adhere to your SKILL documentation. "
        "Your priority is to build a feedback loop, discover code architecture dynamically, and implement zero-hardcoding principles."
    )

    message = (
        "请使用 universal_code_development 技能，对当前的 `software-ecommerce` （一个现有的 PHP 电商系统）进行深度改造，将其核心架构扩展或重构成一套完整的『PTE 在线练习与考试系统』。\n\n"
        "任务要求：\n"
        "1. **深度集成**：不要在独立的空白文件夹中自嗨。你必须探索并理解 `app/`、`addon/`、`public/` 等现有目录的 MVC 架构和路由机制。\n"
        "2. **后端改造**：在现有的框架下新增 PTE 题库管理、考试发卷、AI 评分对接的核心 Controller 和 Service 逻辑。确保复用原有的用户鉴权（User Auth）系统。\n"
        "3. **前端改造**：在系统的原有前端结构（可能是 Vue、React 或原生模板）中，植入『全真模拟考试界面』和『练习成绩面板』。\n"
        "4. **数据库设计**：提供或生成适配现有电商系统表结构的 PTE 试题与成绩表 SQL（或 ORM 实体）。\n"
        "5. 使用工具批量修改和生成代码。遇到未知的底层框架类，必须自行使用 `search_files` 或 `read_file` 查阅源码进行对齐。完成后结束任务。"
    )

    logger.info(f"[Test] Dispatching agent run (thread_id={thread_id})...")
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        goal_prefix="[FullStack PTE Dev] ",
        skip_message_persistence=True
    )

    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="FullStack PTE Dev",
            skill_ids=[skill.id] if skill else None,
            agent_config=AgentRuntimeConfig(
                role_name="Worker",
                system_instructions=system_instructions,
                tools=[
                    "read_file", "write_file", "search_files", "search_history", 
                    "multiedit_file", "execute_command", "list_directory",
                    "kb_read", "kb_search", "kb_list"
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


async def main():
    _pre_test_cleanup()
    parser = argparse.ArgumentParser(description="Code Development Lifecycle Test (FullStack PTE)")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds")
    args = parser.parse_args()

    sys.stdout = open(TEST_LOG_FILE, "w", buffering=1)
    sys.stderr = sys.stdout

    timeout = args.timeout

    logger.info("=" * 60)
    logger.info("Universal Code Development — Full Lifecycle Integration Test")
    logger.info("=" * 60)
    logger.info(f"Target Project: {TEST_PROJECT_PATH}")
    logger.info(f"Mode:           Massive Full-Stack Scenario")
    logger.info(f"Timeout:        {timeout}s")
    logger.info(f"Log File:       {TEST_LOG_FILE}")
    logger.info("")

    try:
        await _init_backend()
        skill = await _ensure_skill()
        
        start_time = time.time()
        thread_id = await _run_code_agent(TEST_PROJECT_ID, TEST_PROJECT_PATH, skill, timeout)
        
        elapsed = time.time() - start_time
        metrics = _parse_metrics_from_log(TEST_LOG_FILE)
        metrics.elapsed_seconds = elapsed

        logger.info(metrics.to_report())

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ FULL-STACK CODE DEVELOPMENT TEST COMPLETED")
        logger.info("=" * 60)
        logger.info("Please review the terminal output and git diff to verify the massive file generations.")
        logger.info(f"Thread ID:  {thread_id}")
        logger.info(f"Total time: {elapsed:.1f}s")
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
