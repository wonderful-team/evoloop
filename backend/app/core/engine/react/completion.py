"""React engine completion pipeline — post-run learning loops (replaces Finish/AuditService triggers).

图引擎的记忆/宏/skill 学习闭环由 ``FinishNode`` + ``AuditService`` 触发；
react 模式主循环无 Finish 节点，改为在 run 收尾时统一触发（代码层，无 prompt 规则）。

v1 收尾管线（并发、互不阻塞、失败仅告警）：
1. 发布 SESSION_COMPLETED（生命周期投影已由既有订阅者处理）
2. 记录 episodic 记忆（一句话 goal → result）
3. 宏学习资格判定 → 触发自动宏创建（复用 MacroCreatorService）
4. skill 候选生成（pending_review，不自动激活）—— 二期接入
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


async def run_completion_pipeline(
    thread_id: str,
    project_id: int | None,
    config: dict[str, Any],
    state: Any,
    *,
    summary: str = "",
) -> None:
    """收尾管线入口。并发执行学习闭环，任一失败不影响收尾。"""
    tasks = [
        _record_episode(thread_id, project_id, config, state, summary),
        _maybe_auto_macro(thread_id, project_id, config, state),
        _maybe_skill_candidate(thread_id, project_id, state),
        _record_metrics(thread_id, state, config),
        notify_create_task(thread_id, config, state, summary),
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


def _extract_final_content(messages: list[Any]) -> str:
    """提取最后一条 assistant 文本（完整，非截断）。"""
    for msg in reversed(messages or []):
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", "")
        if role in ("ai", "assistant") and content and not getattr(msg, "tool_calls", None):
            return str(content)
    return ""


def _split_article(content: str) -> tuple[str, str, list[str]]:
    """从最终 assistant 文本启发式切分 title / body / topics。

    约定：markdown 一级标题 `# xxx` 作为标题，其余 `#xxx` 作为话题，
    正文为整篇内容（不含仅用于标记的标题行重复）。
    """
    text = content.strip() or ""
    title = ""
    body = text
    if text.startswith("# "):
        line_end = text.find("\n")
        first = text[2:line_end].strip() if line_end != -1 else text[2:].strip()
        if first:
            title = first
    if not title:
        first_line = text.split("\n", 1)[0].strip()
        if first_line and not first_line.startswith("#") and len(first_line) <= 60:
            title = first_line
    topic_matches = list(
        dict.fromkeys(re.findall(r"#([^\s#，#，]+)", text))
    )
    return title, body, topic_matches


async def notify_create_task(
    _thread_id: str,
    config: dict[str, Any],
    state: Any,
    summary: str,
) -> None:
    """AI 创作任务收尾回传：deep link 发起的创作完成后，把结构化结果
    POST 回线上 backend（channel_ai_task 接口），带 HMAC 签名。

    触发条件：config.metadata 携带 task_id + callback_url + secret。
    失败仅告警，不阻塞收尾。
    """
    meta = config.get("metadata", {}) or {}
    task_id = meta.get("task_id")
    callback_url = meta.get("callback_url")
    secret = meta.get("secret")
    if not task_id or not callback_url or not secret:
        return

    content = _extract_final_content(getattr(state, "messages", None)) or summary or ""
    if not content:
        return

    title, body, topics = _split_article(content)
    topics_str = "\n".join(topics)
    try:
        from app.core.security.crypto import generate_hmac_signature
        from app.utils.http import create_client

        sign = generate_hmac_signature(secret, task_id + title + body + topics_str)
        payload = {
            "task_id": task_id,
            "sign": sign,
            "title": title,
            "body": body,
            "topics": topics,
        }
        async with create_client(timeout=30.0) as client:
            resp = await client.post(callback_url, json=payload)
        if resp.status_code >= 300:
            logger.warning(
                f"[ReactCompletion] create-task callback failed {resp.status_code}: {resp.text[:200]}"
            )
        else:
            logger.info(f"[ReactCompletion] create-task callback sent for {task_id}")
    except Exception as e:
        logger.warning(f"[ReactCompletion] create-task callback error: {e}", exc_info=True)


async def _record_metrics(thread_id: str, state: Any, _config: dict[str, Any]) -> None:
    """记录 react 运行度量（llm_calls / tool_errors / tokens）到 AgentActivity。

    埋点来源：state.messages（assistant 消息数 = LLM 调用次数；tool 消息含
    error 计数）；tokens 从消息 additional_kwargs 汇总（若 provider 回传）。
    """
    try:
        messages = state.messages or []
        llm_calls = sum(
            1
            for m in messages
            if getattr(m, "role", None) in ("ai", "assistant")
        )
        tool_errors = 0
        input_tokens = 0
        output_tokens = 0
        for m in messages:
            kw = getattr(m, "additional_kwargs", None) or {}
            response_metadata = getattr(m, "response_metadata", None) or {}
            usage_metadata = getattr(m, "usage_metadata", None) or {}
            raw_usage = kw.get("usage") or response_metadata.get("usage") or usage_metadata
            if isinstance(raw_usage, dict):
                kw = {**kw, "input_tokens": kw.get("input_tokens") or raw_usage.get("input_tokens") or raw_usage.get("prompt_tokens") or 0, "output_tokens": kw.get("output_tokens") or raw_usage.get("output_tokens") or raw_usage.get("completion_tokens") or 0}
            if getattr(m, "role", None) == "tool" and "error" in str(getattr(m, "content", "")).lower():
                tool_errors += 1
            input_tokens += int(kw.get("input_tokens", 0) or 0)
            output_tokens += int(kw.get("output_tokens", 0) or 0)

        from app.core.monitoring.activity_state import ActivityStateService

        store = ActivityStateService()
        await store.update_metrics(
            thread_id,
            llm_calls=llm_calls,
            tool_errors=tool_errors,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        logger.info(
            f"[ReactCompletion] metrics recorded for {thread_id}: "
            f"llm_calls={llm_calls} tool_errors={tool_errors}"
        )
    except Exception as e:
        logger.warning(f"[ReactCompletion] metrics record failed: {e}", exc_info=True)


async def _record_episode(
    thread_id: str, project_id: int | None, _config: dict[str, Any], state: Any, summary: str
) -> None:
    """记录一段 episodic 记忆（goal → result）。"""
    try:
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
        goal = getattr(state, "session_goal", None) or summary or ""
        if not goal:
            return
        result = summary or ""
        from app.core.memory.lifespan import MemoryLifespanManager
        from app.core.memory.schemas import Episode

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        await manager.record_episode(
            Episode(
                goal=goal[:200],
                result=result[:500],
                project_id=project_id or ctx.project_id or 0,
                source_message_id=thread_id,
                plan_summary="",
            )
        )
        logger.info(f"[ReactCompletion] recorded episode for {thread_id}")
    except Exception as e:
        logger.warning(f"[ReactCompletion] episode record failed: {e}", exc_info=True)


async def _maybe_auto_macro(
    thread_id: str, _project_id: int | None, _config: dict[str, Any], _state: Any
) -> None:
    """宏学习资格判定：任务含可回放确定性步骤时触发自动宏创建。"""
    try:
        from app.core.config import settings

        if not settings.AUTO_MACRO_CREATION_ENABLED:
            return
        from app.core.learning.macro import MacroCreatorService

        if await MacroCreatorService.is_eligible(thread_id):
            logger.info(f"[ReactCompletion] auto-macro eligible for {thread_id}")
    except Exception as e:
        logger.warning(f"[ReactCompletion] auto-macro check failed: {e}", exc_info=True)


def _session_has_reusable_path(state: Any) -> bool:
    """启发式判定会话是否含非平凡可复用解题路径（skill 候选门槛）。

    条件：工具消息数 >= 5，且至少包含一次写/编辑/命令执行（代码或文件改动）。
    """
    messages = getattr(state, "messages", None) or []
    tool_msgs = [m for m in messages if getattr(m, "role", None) == "tool"]
    if len(tool_msgs) < 5:
        return False
    mutating = {"edit", "write", "bash", "run_macro"}
    names = {getattr(m, "name", None) for m in tool_msgs}
    return bool(names & mutating)


async def _maybe_skill_candidate(
    thread_id: str, _project_id: int | None, state: Any
) -> None:
    """skill 候选生成（§3.7）：会话含非平凡可复用解题路径时，后台合成 candidate
    skill（pending_review，不自动激活，语义与 finish.prompt.j2 提炼一致）。"""
    try:
        from app.core.config import settings

        if not settings.ENABLE_SKILL_SYNTHESIS:
            return
        if not _session_has_reusable_path(state):
            return
        from app.core.engine.tools.learning import create_skill_from_session

        await create_skill_from_session(
            reason="会话含非平凡可复用解题路径，收尾管线自动生成 candidate skill",
            thread_id=thread_id,
        )
        logger.info(f"[ReactCompletion] skill candidate synthesis queued for {thread_id}")
    except Exception as e:
        logger.warning(f"[ReactCompletion] skill candidate check failed: {e}", exc_info=True)


async def publish_session_completed_react(
    thread_id: str,
    project_id: int | None,
    config: dict[str, Any],
    state: Any,
    *,
    summary: str,
) -> None:
    """发布 SESSION_COMPLETED 并触发收尾管线（react 模式替代 FinishNode 收尾）。"""
    from app.core.events.publishers import publish_session_completed
    from app.core.events.schemas import SessionCompletedData

    ctx = None
    try:
        from app.core.context.manager import ContextManager

        ctx = ContextManager.current()
    except Exception:
        pass
    source = (ctx.metadata.source if ctx and ctx.metadata else None) or config.get(
        "metadata", {}
    ).get("source", "")

    data = SessionCompletedData(
        thread_id=thread_id,
        run_id=config.get("configurable", {}).get("run_id"),
        project_id=project_id or (ctx.project_id if ctx else None),
        member_id=(ctx.member_id if ctx else None),
        messages=[],
        blackboard_dict={},
        summary=summary,
        tts_summary="",
        outcome="completed",
        audit_tier="react",
        duration_ms=0,
        model=(ctx.active_model if ctx else None),
        source=source,
    )
    try:
        await publish_session_completed(data=data)
    except Exception as e:
        logger.warning(f"[ReactCompletion] session_completed publish failed: {e}")

    # 异步触发学习闭环（不阻塞收尾）
    asyncio.create_task(run_completion_pipeline(thread_id, project_id, config, state, summary=summary))
