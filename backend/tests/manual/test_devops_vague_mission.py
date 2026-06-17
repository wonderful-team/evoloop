#!/usr/bin/env python3
"""
DevOps Vague Mission — 对话式运维推理集成测试

场景：用户说了一句模糊的 "帮我把前端打包部署到客户的服务器上"
Agent 需要：
  1. 识别运维需求，触发了 DevOps 技能
  2. 自主发现项目信息（deploy/profiles/ 中的客户配置、密码箱等）
  3. 信息不足时主动询问（打包哪个部分？哪个客户？服务器连接信息？）
  4. 前置条件齐备后才开始执行
  5. 执行过程中遇到失败，询问用户意见
  6. 最终完成部署（或报告失败原因）

测试方法：通过智能 HITL 自动应答，模拟真实用户回复 Agent 的问题。
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

_LOG_DIR = os.path.join(os.path.dirname(__file__), ".logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_RUN_TS = str(int(time.time()))
LOG_FILE = os.path.join(_LOG_DIR, f"vague_mission_{_RUN_TS}.log")

_stdout_orig = sys.stdout
_log_fh = open(LOG_FILE, "w", encoding="utf-8")

class _Tee:
    def write(self, msg):
        _log_fh.write(msg)
        _stdout_orig.write(msg)
    def flush(self):
        _log_fh.flush()
        _stdout_orig.flush()

sys.stdout = _Tee()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],  # Explicitly use stdout (Tee)
    force=True,
)
logger = logging.getLogger("devops_vague_mission")

logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("passlib").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

print(f"📝 Log file: {LOG_FILE}")

EVOLOOP_ROOT = "/Users/xujin/Projects/evoloop"
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

DEFAULT_MODEL = "kimi-k2-thinking-turbo"
DEFAULT_TIMEOUT = 1800
PROJECT_ID = 57


@dataclass
class ConversationTrace:
    turns: list[dict] = field(default_factory=list)
    agent_questions: list[str] = field(default_factory=list)
    user_answers: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    worker_responses: list[str] = field(default_factory=list)
    supervisor_route: dict | None = None
    errors: list[str] = field(default_factory=list)
    elapsed: float = 0.0
    commands: list[str] = field(default_factory=list)  # Track execute_command commands

    def add_hitl(self, question: str, answer: str):
        self.agent_questions.append(question)
        self.user_answers.append(answer)
        self.turns.append({"type": "hitl", "question": question, "answer": answer})

    def add_tool(self, tool_name: str, args: dict, result: str):
        self.tool_calls.append({"tool": tool_name, "args": args, "result": result[:200]})
        if tool_name == "execute_command" and args.get("command"):
            self.commands.append(args["command"])

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "对话式运维 — 执行轨迹",
            "=" * 60,
            f"总耗时: {self.elapsed:.1f}s",
            f"Agent 提问次数: {len(self.agent_questions)}",
            f"工具调用次数: {len(self.tool_calls)}",
        ]
        for i, q in enumerate(self.agent_questions):
            lines.append(f"\n  🗣 Round {i+1}: Agent 问 → {q[:120]}")
            lines.append(f"     User 答 → {self.user_answers[i][:120]}")
        lines.append("\n  🛠 工具调用:")
        for t in self.tool_calls:
            lines.append(f"    {t['tool']}: {str(t['args'])[:120]}")
        if self.errors:
            lines.append("\n  ❌ 错误:")
            for e in self.errors:
                lines.append(f"    - {e}")
        lines.append("=" * 60)
        return "\n".join(lines)


async def init_backend():
    from app.infrastructure.database.resource_manager import db_resource_manager
    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=True, seed_data=True)

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken(project_id=PROJECT_ID)

    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    logger.info("[Test] Building agent graph...")
    builder = GraphBuilder()
    config_path = os.path.join(BACKEND_ROOT, "app/core/engine/config/agent_main.yaml")
    workflow = builder.build(os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)
    set_graph(workflow)
    logger.info("[Test] Agent graph ready.")


def smart_answer(prompt: str) -> str | None:
    """Match agent ask_human prompts to pre-defined answers."""
    p = prompt.lower()
    if any(kw in p for kw in ["打包什么", "哪个部分", "构建目标", "打包哪个", "什么目标"]):
        return "前端"
    if any(kw in p for kw in ["哪个客户", "客户名称", "哪个客户", "客户标识"]):
        return "customer_a"
    if any(kw in p for kw in ["服务器", "ip", "ssh", "连接信息", "主机", "地址"]):
        return "服务器 IP 192.168.1.100，SSH 密钥 ~/.ssh/test_key，用户 root"
    if any(kw in p for kw in ["检查配置", "先检查", "配置检查", "校验"]):
        return "检查一下吧"
    if any(kw in p for kw in ["修复", "错误", "编译失败", "失败", "重试"]):
        return "是，修复后重试"
    if any(kw in p for kw in ["继续", "确认", "执行"]) or "?" not in p:
        return None
    return None


async def run_agent_turn(
    thread_id: str,
    message: str,
    turn_name: str,
    trace: ConversationTrace,
    setup_blackboard: bool = False,
) -> bool:
    """
    Run one turn of the conversation.
    Returns True if the agent executed commands in this turn.
    """
    from langchain_core.messages import ToolMessage
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.hitl.orchestrator import HITLOrchestrator, get_pending_hitl_call
    from app.core.engine.state.blackboard import BlackboardState
    from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket, TicketParameters
    from app.core.globals import get_graph

    thread_context_store.set_working_directory(thread_id, EVOLOOP_ROOT)

    logger.info(f"\n{'='*60}")
    logger.info(f">>> {turn_name}: {message}")
    logger.info(f"{'='*60}")

    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=PROJECT_ID,
        model=DEFAULT_MODEL,
        goal_prefix=f"[DevOps {turn_name}] ",
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    # Only setup blackboard on first turn
    if setup_blackboard:
        skills_result = await get_skills()
        devops_skill = next((s for s in skills_result if "devops" in s.name.lower()), None)

        blackboard = BlackboardState(
            ticket=ExecutionTicket(
                ticket_type="task",
                topic="DevOps deployment",
                skill_ids=[devops_skill.id] if devops_skill else None,
                agent_config=AgentRuntimeConfig(
                    role_name="Workspace Operator",
                    system_instructions="",
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
        if devops_skill:
            result.inputs["metadata"]["explicit_skills"] = [{
                "id": devops_skill.id,
                "name": devops_skill.name,
                "description": devops_skill.description or "",
            }]
            logger.info(f"[Test] Explicit skill attached: {devops_skill.name} (id={devops_skill.id})")

    logger.info(f"[Test] Running {turn_name}...")
    start = time.time()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs),
            timeout=DEFAULT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        trace.errors.append(f"{turn_name} timed out after {DEFAULT_TIMEOUT}s")
        return False
    elapsed = time.time() - start
    logger.info(f"[Test] {turn_name} completed in {elapsed:.1f}s")

    # Handle HITL loops within this turn
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id, "model": DEFAULT_MODEL}}

    for resume_round in range(15):
        await asyncio.sleep(0.5)
        state = await graph.aget_state(config)

        if not state.next:
            logger.info(f"[Test] {turn_name} graph completed")
            break

        logger.info(f"[Test] {turn_name} paused at: {state.next}")

        pending = await get_pending_hitl_call(graph, config)
        if pending:
            tool_name = pending.get("name", "unknown")
            prompt_text = pending.get("prompt", pending.get("action_description", ""))
            logger.info(f"[Test] HITL: {tool_name} | {prompt_text[:100]}")

            answer = smart_answer(prompt_text) if tool_name == "ask_human" else None
            if answer is None:
                answer = "approved"

            trace.add_hitl(prompt_text, answer)

            normalized = await HITLOrchestrator.handle_resume(thread_id, pending, answer)
            tool_msg = ToolMessage(tool_call_id=pending["id"], content=normalized)

            try:
                await asyncio.wait_for(
                    run_agent_background(thread_id, {
                        "messages": [tool_msg.model_dump()],
                        "project_id": PROJECT_ID,
                        "model": DEFAULT_MODEL,
                        "hitl_resume_response": normalized,
                    }),
                    timeout=DEFAULT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                trace.errors.append(f"{turn_name} resume round {resume_round} timed out")
                break
        else:
            trace.warnings = trace.warnings if hasattr(trace, 'warnings') else []
            trace.warnings.append(f"{turn_name} paused at {state.next} but no HITL found")
            break

    # Check if this turn had any execute_command
    from app.infrastructure.database.sql.database import session_scope
    from app.models import Message
    from sqlalchemy import select

    has_exec = False
    async with session_scope() as session:
        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number)
        res = await session.execute(stmt)
        for m in res.scalars().all():
            if m.tool_name == "execute_command":
                has_exec = True
                trace.add_tool(m.tool_name, {"command": str(m.content)[:100]}, "")
            if m.role == "ai" and m.category == "assistant_response" and m.content and not m.tool_name:
                trace.worker_responses.append(m.content)

    return has_exec


async def run_vague_mission() -> ConversationTrace:
    trace = ConversationTrace()
    start = time.time()

    thread_id = f"devops-vague-{int(time.time())}"

    # Turn 1: Initial task
    turn_1_msg = "打包 MacOS 的桌面端，并将包上传到服务器"
    has_exec = await run_agent_turn(thread_id, turn_1_msg, "Turn-1", trace, setup_blackboard=True)

    # If no commands executed, send Turn 2 to push agent to continue
    if not has_exec:
        logger.info("[Test] Turn 1 did not execute commands. Sending Turn 2 to push agent...")
        turn_2_msg = "请继续执行构建和部署操作，不要只回复文字"
        has_exec = await run_agent_turn(thread_id, turn_2_msg, "Turn-2", trace)

    # If still no commands, try Turn 3
    if not has_exec:
        logger.info("[Test] Turn 2 still did not execute. Sending Turn 3...")
        turn_3_msg = "直接执行构建命令，不要回复确认文字"
        has_exec = await run_agent_turn(thread_id, turn_3_msg, "Turn-3", trace)

    trace.elapsed = time.time() - start

    # Print summary
    logger.info(trace.summary())
    return trace


async def get_skills():
    from sqlalchemy import select

    from app.infrastructure.database.sql.database import session_scope
    from app.models.learning import LearnedSkill
    async with session_scope() as session:
        stmt = select(LearnedSkill).where(LearnedSkill.is_active)
        result = await session.execute(stmt)
        return result.scalars().all()


async def verify_trace(trace: ConversationTrace):
    """Verify the agent demonstrated conversational reasoning."""
    has_questions = len(trace.agent_questions) > 0
    has_exec_tools = any(t["tool"] == "execute_command" for t in trace.tool_calls)

    logger.info("")
    logger.info("=" * 60)
    logger.info("验证结果")
    logger.info("=" * 60)
    logger.info(f"  Agent 是否主动提问: {'✅' if has_questions else '❌'} ({len(trace.agent_questions)} 次)")
    logger.info(f"  Agent 是否执行命令: {'✅' if has_exec_tools else '❌'}")
    if trace.agent_questions:
        q_categories = []
        for q in trace.agent_questions:
            ql = q.lower()
            if any(kw in ql for kw in ["打包", "目标", "前端", "构建"]):
                q_categories.append("目标确认")
            elif any(kw in ql for kw in ["客户"]):
                q_categories.append("客户确认")
            elif any(kw in ql for kw in ["服务器", "ip", "ssh", "主机"]):
                q_categories.append("服务器确认")
            elif any(kw in ql for kw in ["修复", "错误", "重试"]):
                q_categories.append("故障处理")
            else:
                q_categories.append(f"其他: {q[:50]}")
        logger.info(f"  问题覆盖: {', '.join(set(q_categories))}")

    if trace.errors:
        logger.info(f"  错误: {len(trace.errors)} 个")
        for e in trace.errors:
            logger.info(f"    └ {e}")

    logger.info("=" * 60)

    # 检查是否从 deploy/profiles/ 发现了客户（自主发现 vs 假设）
    has_profile_discovery = any(
        "deploy/profiles" in cmd or "customer_test" in cmd
        for cmd in trace.commands
    )

    if not has_questions and has_profile_discovery:
        logger.info("✅ Agent 自主发现客户配置（deploy/profiles/），无需提问直接执行 — 符合预期")
    elif not has_questions:
        logger.warning("Agent 没有主动提问就直接执行了 — 可能使用了默认值，缺少自主发现或对话澄清能力")
    else:
        logger.info("✅ Agent 具备对话式运维推理能力：发现信息不足 → 主动询问 → 收集条件 → 执行")

    return has_questions or has_profile_discovery


async def main():
    from app.infrastructure.database.resource_manager import db_resource_manager

    logger.info("=" * 60)
    logger.info("DevOps 模糊请求 — 对话式运维推理测试")
    logger.info(f"Project ID: {PROJECT_ID}")
    logger.info(f"Model: {DEFAULT_MODEL}")
    logger.info("=" * 60)

    passed = False
    try:
        await init_backend()
        trace = await run_vague_mission()
        passed = await verify_trace(trace)
    finally:
        # Write full trace dump to log file
        logging.getLogger("devops_vague_mission_trace").info(
            "\n" + trace.summary()
        )
        if db_resource_manager.engine is not None:
            await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")

    if passed:
        logger.info("\n✅ 测试通过: Agent 展示了对话式运维能力")
    else:
        logger.warning("\n⚠️ 测试完成: Agent 未展示主动提问能力，详见上方分析")


if __name__ == "__main__":
    asyncio.run(main())
