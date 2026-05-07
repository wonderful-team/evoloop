"""
Memory & Context Management Tools.
Consolidated from core and domain layers for unified architecture.
"""

import json
import logging
import time
import uuid
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import FORGET_SAFETY_WINDOW
from app.core.context.manager import ContextManager
from app.core.memory.backends.sql_short_term import SqlShortTermMemory
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.core.tools.base import evoloop_tool
from app.utils import ContentFormatter
from .retrieval import get_relevant_memories

logger = logging.getLogger(__name__)


# ========================================================================
# 1. Long-term Memory Tools (Remember/Recall)
# ========================================================================

@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.remember"
)
async def remember(content: str, context: str = "", is_user_preference: bool = False) -> str:
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
    user_id = ctx.user_id if ctx else None

    try:
        # Determine memory scope based on LLM's classification
        mem_type = MemoryType.USER if is_user_preference else MemoryType.PROJECT
        privacy = PrivacyLevel.PRIVATE if is_user_preference else PrivacyLevel.TEAM

        title = content[:60] + "..." if len(content) > 60 else content
        full_content = content
        if context:
            full_content += f"\n\nContext: {context}"

        entry_id = f"mem_{uuid.uuid4().hex[:12]}"

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
            user_id=str(user_id) if user_id is not None else None,
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
        logger.error(f"[MemoryTool] Failed to remember: {e}")
        return f"Failed to save memory: {str(e)}"


@evoloop_tool(
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.recall"
)
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
    user_id = ctx.user_id if ctx else None
    project_id = ctx.project_id if ctx else None
    thread_id = ctx.thread_id if ctx else None

    try:
        entries = await get_relevant_memories(
            query=query,
            user_id=user_id,
            project_id=project_id,
            max_results=limit,
        )

        if not entries:
            # Fallback to searching conversation history if no semantic match in long-term
            if thread_id:
                memory = SqlShortTermMemory()
                messages = await memory.search_messages(query, thread_id, limit=5)
                if messages:
                    return ContentFormatter.chat_search_results(query, messages)

            return f"No memories found for '{query}'."

        # Format results
        lines = [f"Recalled {len(entries)} memories:\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"{i}. [{entry.type.value.upper()}] {entry.title} (ID: {entry.id})")
            lines.append(f"   {entry.content[:300]}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[MemoryTool] Recall failed: {e}")
        return f"Failed to recall: {str(e)}"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.forget_memory"
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
        logger.error(f"[MemoryTool] Failed to forget memory: {e}")
        return f"Error deleting memory: {str(e)}"


# ========================================================================
# 2. History Search Tools
# ========================================================================

@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="evoloop.tool_summary.search_history"
)
async def search_history(
    query: str,
    limit: int = 10,
    thread_id: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
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
            return f"No messages found for '{query}' in history."
        return ContentFormatter.chat_search_results(query, results)

    except Exception as e:
        logger.error(f"[MemoryTool] History search failed: {e}")
        return f"Failed to search history: {str(e)}"


# ========================================================================
# 3. Context Management Tools (Active Forgetting)
# ========================================================================

@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.forget_tool_outputs"
)
async def forget_tool_outputs(
    tool_call_ids: Annotated[list[str], "List of tool_call_ids to forget"],
    reason: Annotated[str, "Why these tool outputs are being forgotten"],
    custom_summaries: Annotated[dict[str, str] | None, "Optional custom summaries"] = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Forget (fold) old tool outputs to free context space.

    Use when you have completed an exploration phase and no longer need
    the full content of previous tool outputs. They will be replaced with summaries.

    SAFETY: Can only forget tool outputs older than 5 steps (FORGET_SAFETY_WINDOW).
    """
    thread_id = config.get("configurable", {}).get("thread_id", "unknown") if config else "unknown"

    try:
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message

        async with session_scope() as session:
            stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.sequence_number.asc())
            result = await session.execute(stmt)
            db_messages = result.scalars().all()

        current_step = len(db_messages)
        message_map = {msg.tool_call_id: {"index": i, "msg": msg} for i, msg in enumerate(db_messages) if msg.tool_call_id}

        results = {"forgotten": [], "skipped": []}
        forgotten_records = {}

        for tc_id in tool_call_ids:
            msg_info = message_map.get(tc_id)
            if not msg_info:
                results["skipped"].append({"id": tc_id, "reason": "Not found"})
                continue

            steps_ago = current_step - msg_info["index"]
            if steps_ago <= FORGET_SAFETY_WINDOW:
                results["skipped"].append({"id": tc_id, "reason": f"Too recent ({steps_ago} steps ago)"})
                continue

            msg = msg_info["msg"]
            tool_name = msg.tool_name or "unknown"
            content = msg.content or ""
            summary = custom_summaries.get(tc_id) if custom_summaries else _generate_summary(tool_name, content)

            forgotten_records[tc_id] = {
                "tool_call_id": tc_id,
                "tool_name": tool_name,
                "summary": summary,
                "original_length": len(content),
                "reason": reason,
                "step_index": msg_info["index"],
                "forgotten_at": time.time(),
            }
            results["forgotten"].append({"id": tc_id, "tool": tool_name, "summary": summary, "saved": len(content) - len(summary)})

        total_saved = sum(r["saved"] for r in results["forgotten"])

        # Persist to blackboard so engine's apply_forgotten_status() can see it
        try:
            from app.core.memory.tool_output_memory import ToolOutputMemory
            ctx = ContextManager.current()
            if ctx and ctx.metadata.blackboard:
                existing_data = ctx.metadata.blackboard.metadata.tool_memory or {}
                memory = ToolOutputMemory.from_dict(existing_data)
                for tc_id, record_data in forgotten_records.items():
                    try:
                        memory.mark_forgotten(
                            tool_call_id=tc_id,
                            tool_name=record_data["tool_name"],
                            summary=record_data["summary"],
                            original_length=record_data["original_length"],
                            reason=record_data["reason"],
                            step_index=record_data["step_index"],
                        )
                    except ValueError:
                        pass  # Already forgotten
                ctx.metadata.blackboard.metadata.tool_memory = memory.to_dict()
        except Exception as e:
            logger.warning(f"[ContextMgmt] Failed to persist tool_memory: {e}")

        return json.dumps({
            "status": "success",
            "message": f"Successfully forgot {len(results['forgotten'])} outputs, saved {total_saved} chars.",
            "_signal": "forget_tool_outputs",
            "data": {
                "forgotten_records": forgotten_records,
                "total_saved": total_saved,
                "reason": reason,
            }
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[ContextMgmt] Forget failed: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.recall_tool_output"
)
async def recall_tool_output(
    tool_call_id: Annotated[str, "The tool_call_id to recall"],
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """Recall a forgotten tool output, restoring its full content to context."""
    thread_id = config.get("configurable", {}).get("thread_id", "unknown") if config else "unknown"

    try:
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message

        async with session_scope() as session:
            stmt = select(Message).where(Message.thread_id == thread_id, Message.tool_call_id == tool_call_id).limit(1)
            result = await session.execute(stmt)
            msg = result.scalar_one_or_none()

            if not msg or not msg.content:
                return json.dumps({"status": "error", "message": "Content not found", "_signal": "recall_tool_output"})

            # Remove from blackboard tool_memory so engine stops replacing with summary
            try:
                from app.core.memory.tool_output_memory import ToolOutputMemory
                ctx = ContextManager.current()
                if ctx and ctx.metadata.blackboard:
                    existing_data = ctx.metadata.blackboard.metadata.tool_memory or {}
                    memory = ToolOutputMemory.from_dict(existing_data)
                    memory.remove_from_forgotten(tool_call_id)
                    ctx.metadata.blackboard.metadata.tool_memory = memory.to_dict()
            except Exception as e:
                logger.warning(f"[ContextMgmt] Failed to update tool_memory on recall: {e}")

            return json.dumps({
                "status": "success",
                "message": f"Recalled content for {tool_call_id} (Length: {len(msg.content)})",
                "_signal": "recall_tool_output",
                "data": {"tool_call_id": tool_call_id, "found": True, "content": msg.content}
            }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[ContextMgmt] Recall failed: {e}")
        return json.dumps({"status": "error", "message": str(e)})


@evoloop_tool(
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.list_forgotten_outputs"
)
async def list_forgotten_outputs(
    limit: Annotated[int, "Max records to return"] = 20,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """List all previously forgotten tool outputs in the current conversation."""
    ctx = ContextManager.current()
    if ctx is None:
        return "Error: No ContextManager available."

    blackboard = ctx.metadata.blackboard
    bb_metadata = blackboard.metadata.model_dump() if blackboard and blackboard.metadata else {}
    tool_memory_data = bb_metadata.get("tool_memory")

    if not tool_memory_data:
        return "No forgotten tool outputs in current context."

    from app.core.memory.tool_output_memory import ToolOutputMemory

    try:
        memory = ToolOutputMemory.from_dict(tool_memory_data)
        forgotten_records = memory.list_forgotten(limit=limit)

        if not forgotten_records:
            return "No forgotten tool outputs in current context."

        lines = [f"### Forgotten Tool Outputs ({len(forgotten_records)})"]
        for record in forgotten_records:
            lines.append(f"- **ID**: {record.tool_call_id}")
            lines.append(f"  **Tool**: {record.tool_name}")
            lines.append(f"  **Reason**: {record.reason}")
            lines.append(f"  **Summary**: {record.summary[:100]}...")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[ContextMgmt] List forgotten failed: {e}")
        return f"Error retrieving forgotten outputs: {str(e)}"


def _generate_summary(tool_name: str, content: str, max_length: int = 200) -> str:
    """Internal helper to generate summaries for forgotten tool outputs."""
    if not content:
        return f"[{tool_name}: empty]"
    if len(content) <= max_length:
        return f"[{tool_name}: {content}]"

    if tool_name == "read_file":
        lines = content.split('\n')
        return f"[read_file: {len(lines)} lines] {lines[0][:80]}..."
    elif tool_name == "list_directory":
        items = [l for l in content.split('\n') if l.strip()]
        return f"[list_directory: {len(items)} items] {', '.join(items[:3])}..."

    return f"[{tool_name}: {len(content)} chars] {content[:max_length]}..."
