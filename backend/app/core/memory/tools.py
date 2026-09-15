"""
Memory & Context Management Tools.
Consolidated from core and domain layers for unified architecture.
"""

import logging

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.memory.constants import (
    DEFAULT_SEARCH_LIMIT,
    get_memory_tools,
    register_memory_tools,
)
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.core.memory.short_term import SqlShortTermMemory
from app.core.tools import evoloop_tool
from app.utils.id import gen_uuid_hex
from app.utils.search_results_formatter import format_chat_search_results

from .retrieval import get_relevant_memories

logger = logging.getLogger(__name__)


# ========================================================================
# 1. Cross-Task Handover Tools
# ========================================================================


@evoloop_tool(
    is_state_mutating=True, summary_template="evoloop.tool_summary.write_handover_notes"
)
async def write_handover_notes(notes: str, key: str = "general") -> str:
    """
    Leave critical handover notes (like API contracts, architecture decisions)
    for the next agent to read. This is a short-term memory explicitly
    passed to subsequent tasks in this workflow.

    Use this when you have finished designing an interface, API, or component,
    and you know a future step will need to consume it.

    Args:
        notes: The critical information to pass on.
        key: Category or name of the component (e.g., "PTEExam_API").
    """
    try:
        ctx = ContextManager.current()
        # 冗余清理：原经 ctx.metadata.blackboard（整个 state 的 duck-typing
        # 挂载）取 shared_context——为读一个字段把全量对话历史每轮写进
        # Redis。shared_context 已由 hydrator 单独同步到 ctx.metadata，直读。
        if ctx and ctx.metadata.shared_context:
            shared = dict(ctx.metadata.shared_context or {})
            shared[key] = notes
            ctx.metadata.shared_context = shared
            logger.info(f"[MemoryTool] Wrote handover notes for key: {key}")
            return f"Successfully saved handover notes under key '{key}'."
        return "Error: State context not available."
    except Exception as e:
        logger.exception(f"[MemoryTool] Failed to write handover notes: {e}")
        return f"Failed to write handover notes: {str(e)}"


# ========================================================================
# 2. Long-term Memory Tools (Remember/Recall)
# ========================================================================


@evoloop_tool(is_state_mutating=True, summary_template="evoloop.tool_summary.remember")
async def remember(
    content: str, context: str = "", is_user_preference: bool = False
) -> str:
    """
    Save important information to long-term memory.

    Use when the user explicitly asks you to remember something:
    - "Remember that I prefer X"
    - "Keep this in mind for next time"
    - "Don't forget this approach"
    - "This is important"

    The content will be automatically available in future conversations.

    Args:
        content: The information to remember.
        context: Optional context about when/why this matters.
        is_user_preference: Set to True if this is about the user's personal preferences, habits, or roles. False for project-specific knowledge.
    """
    ctx = ContextManager.current()
    member_id = ctx.member_id if ctx else None

    try:
        # Determine memory scope based on LLM's classification
        mem_type = MemoryType.USER if is_user_preference else MemoryType.PROJECT
        privacy = PrivacyLevel.PRIVATE if is_user_preference else PrivacyLevel.TEAM

        title = content[:60] + "..." if len(content) > 60 else content
        full_content = content
        if context:
            full_content += f"\n\nContext: {context}"

        entry_id = f"mem_{gen_uuid_hex()[:12]}"

        # Ensure IDs are types that MemoryEntry expects (support mocks in tests)
        project_id = int(ctx.project_id) if ctx and ctx.project_id is not None else None

        run_id = ctx.run_id if ctx else None

        entry = MemoryEntry(
            id=entry_id,
            type=mem_type,
            privacy=privacy,
            title=title,
            content=full_content,
            description=content[:200],
            member_id=member_id,
            project_id=project_id,
            tags=["remembered"],
            source="agent_tool",
            source_message_id=str(run_id) if run_id else None,
            run_id=str(run_id) if run_id else None,
        )

        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        await manager.save_memory(entry)

        logger.info(f"[MemoryTool] Remembered: {title[:40]}... (ID: {entry_id})")
        return f"Remembered: {title} (ID: {entry_id})"

    except Exception as e:
        logger.exception(f"[MemoryTool] Failed to remember: {e}")
        return f"Failed to save memory: {str(e)}"


@evoloop_tool(is_state_mutating=False, summary_template="evoloop.tool_summary.recall")
async def recall(query: str, limit: int = 5) -> str:
    """
    Search memory for previously remembered information.

    Use when:
    - User asks "What did we discuss about X?"
    - User says "Remember that pattern we used?"
    - You need context from previous conversations

    Args:
        query: What to recall/search for.
        limit: Max results to return.
    """
    ctx = ContextManager.current()
    member_id = ctx.member_id if ctx else None
    project_id = ctx.project_id if ctx else None
    thread_id = ctx.thread_id if ctx else None

    try:
        entries = await get_relevant_memories(
            query=query,
            member_id=member_id,
            project_id=project_id,
            max_results=limit,
        )

        if not entries:
            # Fallback to searching conversation history if no semantic match in long-term
            if thread_id:
                memory = SqlShortTermMemory()
                messages = await memory.search_messages(query, thread_id, limit=5)
                if messages:
                    return format_chat_search_results(query, messages)

            return f"No memories found for '{query}'.", {"count": 0}

        # Format results
        lines = [f"Recalled {len(entries)} memories:\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(
                f"{i}. [{entry.type.value.upper()}] {entry.title} (ID: {entry.id})"
            )
            lines.append(f"   {entry.content[:300]}")
            lines.append("")

        return "\n".join(lines), {"count": len(entries)}

    except Exception as e:
        logger.exception(f"[MemoryTool] Recall failed: {e}")
        return f"Failed to recall: {str(e)}"


@evoloop_tool(
    is_state_mutating=True, summary_template="evoloop.tool_summary.forget_memory"
)
async def forget_memory(memory_id: str) -> str:
    """
    Delete a specific long-term memory by its ID.

    Use when:
    - User says "Forget about X" or "Delete that memory about Y"
    - You realize a previously stored piece of information is now completely wrong or irrelevant.

    Args:
        memory_id: The unique ID of the memory to delete (must be obtained via recall first).
    """
    try:
        from app.core.memory.lifespan import MemoryLifespanManager

        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager

        success = await manager.delete(memory_id)
        if success:
            logger.info(f"[MemoryTool] Forgotten memory: {memory_id}")
            return f"Memory '{memory_id}' has been permanently forgotten."
        else:
            return f"Could not find memory with ID '{memory_id}' to delete."

    except Exception as e:
        logger.exception(f"[MemoryTool] Failed to forget memory: {e}")
        return f"Error deleting memory: {str(e)}"


# ========================================================================
# 2. History Search Tools
# ========================================================================


@evoloop_tool(
    is_memory_tool=True, summary_template="evoloop.tool_summary.search_history"
)
async def search_history(
    query: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    thread_id: str | None = None,
) -> str:
    """
    Search conversation history for specific keywords or topics.
    Useful for recalling past decisions, requirements, or code snippets discussed earlier.

    CRITICAL: This tool automatically searches the CURRENT conversation thread by default.
    You DO NOT need to provide thread_id unless you want to search a different conversation.

    WHEN TO USE:
    - User refers to "之前说的" / "刚才讨论的" / "第X轮" / "earlier" / "previously"
    - Current context window handles recent messages, use this for older messages.

    KEYWORD EXTRACTION STRATEGY:
    The search uses SQL LIKE matching. Extract CORE CONCEPTS:
    - GOOD: "PostgreSQL", "auth_service", "Dockerfile"
    - BAD: "第3轮", "刚才说的" (Position references won't match technical content)
    """
    if not query:
        return "Error: query is required."

    ctx = ContextManager.current()
    target_thread = thread_id or ctx.thread_id
    if not target_thread:
        return "Error: No active conversation found to search history."

    try:
        memory = SqlShortTermMemory()
        results = await memory.search_messages(query, target_thread, limit)
        if not results:
            return f"No messages found for '{query}' in history.", {
                "count": 0,
                "top_k": limit,
            }
        text, meta = format_chat_search_results(query, results)
        meta["top_k"] = limit
        return text, meta

    except Exception as e:
        logger.exception(f"[MemoryTool] History search failed: {e}")
        return f"Failed to search history: {str(e)}"


# ========================================================================
# 3. Context Management Tools (Active Forgetting)
# ========================================================================
# 主动遗忘能力已移入代码层自动管理（executor 统一截断 + react/truncate.py），
# forget_tool_outputs / recall_tool_output / list_forgotten_outputs 不再作为
# Agent 工具暴露（§6）。


# Register memory tools for gating by ENABLE_MEMORY setting
register_memory_tools(
    write_handover_notes,
    remember,
    recall,
    forget_memory,
    search_history,
)

# 门控：ENABLE_MEMORY 关闭时禁用全部记忆工具（不读取、不写入、不暴露）。
for _tool in get_memory_tools():
    _wrapped = getattr(_tool, "func", None)
    if _wrapped is not None:
        _wrapped.is_evoloop_active = settings.ENABLE_MEMORY
