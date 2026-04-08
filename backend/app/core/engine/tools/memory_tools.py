"""
Memory Tools - Simple remember/recall for Agent conversations.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from app.core.context.manager import ContextManager
from app.core.memory import get_relevant_memories
from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.core.tools.base import evoloop_tool
from app.core.memory import MemoryContainer, MemoryConfig

logger = logging.getLogger(__name__)


class RememberInput(BaseModel):
    content: str = Field(..., description="The information to remember")
    context: str = Field("", description="Optional context about when/why this matters")


@evoloop_tool(
    args_schema=RememberInput,
    is_state_mutating=True,
    name_map={"zh": "记住", "en": "Remember"}
)
async def remember(content: str, context: str = "") -> str:
    """
    Save important information to long-term memory.
    
    Use when the user explicitly asks you to remember something:
    - "Remember that I prefer X"
    - "Keep this in mind for next time"  
    - "Don't forget this approach"
    - "This is important"
    
    The content will be automatically available in future conversations.
    
    Args:
        content: What to remember (the key fact/pattern/rule)
        context: Optional context about when/why this matters
    """
    ctx = ContextManager.current()
    user_id = ctx.user_id if ctx else None
    project_id = ctx.project_id if ctx else None
    
    try:
        # Determine if this is user preference or project knowledge
        is_user_preference = any(kw in content.lower() for kw in [
            "prefer", "like", "want", "don't want", "always", "never", "i am", "i'm", "my "
        ])
        
        mem_type = MemoryType.USER if is_user_preference else MemoryType.PROJECT
        privacy = PrivacyLevel.PRIVATE if is_user_preference else PrivacyLevel.TEAM
        
        # Generate simple title from content
        title = content[:60] + "..." if len(content) > 60 else content
        
        # Build full content
        full_content = content
        if context:
            full_content += f"\n\nContext: {context}"
        
        # Generate unique ID using UUID to avoid collisions
        import uuid
        entry_id = f"mem_{uuid.uuid4().hex[:12]}"
        
        entry = MemoryEntry(
            id=entry_id,
            type=mem_type,
            privacy=privacy,
            title=title,
            content=full_content,
            description=content[:200],
            user_id=user_id,
            project_id=project_id,
            tags=["remembered"],
            source="agent_tool",
        )
        
        # Use MemoryContainer pattern
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        manager = container.memory_manager
        await manager.save_memory(entry)
        logger.info(f"[MemoryTool] Remembered: {title[:40]}...")
        return f"Remembered: {title}"
        
    except Exception as e:
        logger.error(f"[MemoryTool] Failed: {e}")
        return f"Failed to save: {str(e)}"


class RecallInput(BaseModel):
    query: str = Field(..., description="What to recall/search for")
    limit: int = Field(5, description="Max results to return")


@evoloop_tool(
    args_schema=RecallInput,
    is_state_mutating=False,
    name_map={"zh": "回忆", "en": "Recall"}
)
async def recall(query: str, limit: int = 5) -> str:
    """
    Search memory for previously remembered information.
    
    Use when:
    - User asks "What did we discuss about X?"
    - User says "Remember that pattern we used?"
    - You need context from previous conversations
    - User refers to "what I told you before"
    
    Args:
        query: Keywords to search for (e.g., "Docker setup", "API pattern")
        limit: Maximum number of results (default 5)
    
    Returns:
        Previously remembered information matching the query
    """
    ctx = ContextManager.current()
    user_id = ctx.user_id if ctx else None
    project_id = ctx.project_id if ctx else None
    thread_id = ctx.thread_id if ctx else None
    
    try:
        # Use smart retrieval with LLM-assisted selection
        entries = await get_relevant_memories(
            query=query,
            user_id=user_id,
            project_id=project_id,
            max_results=limit,
        )
        
        if not entries:
            # Also try searching conversation history
            from app.core.memory.backends.sql_short_term import SqlShortTermMemory
            short_term = SqlShortTermMemory()
            
            if thread_id:
                messages = await short_term.search_messages(query, thread_id, limit=5)
                if messages:
                    lines = ["Found in current conversation:\n"]
                    for msg in messages[:3]:
                        role = "User" if msg.type == "human" else "You"
                        content = str(msg.content)[:200].replace('\n', ' ')
                        lines.append(f"- [{role}]: {content}...")
                    return "\n".join(lines)
            
            return f"No memories found for '{query}'."
        
        # Format results
        lines = [f"Recalled {len(entries)} memories:\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"{i}. [{entry.type.value.upper()}] {entry.title}")
            lines.append(f"   {entry.content[:300]}")
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"[MemoryTool] Recall failed: {e}")
        return f"Failed to recall: {str(e)}"


class SearchHistoryInput(BaseModel):
    query: str = Field(..., description="Keywords to search in conversation history")


@evoloop_tool(
    args_schema=SearchHistoryInput,
    is_state_mutating=False,
    name_map={"zh": "搜索对话历史", "en": "Search History"}
)
async def search_history(query: str) -> str:
    """
    Search current conversation history for earlier messages.
    
    CRITICAL: Use when user refers to earlier discussion:
    - "第3轮的方案"
    - "之前说的" 
    - "回到刚才"
    - "你之前提到的"
    
    The context window may have truncated that information.
    
    Args:
        query: Keywords from user's reference (e.g., "PostgreSQL", "Dockerfile")
    
    Returns:
        Matching messages from earlier in the conversation
    """
    ctx = ContextManager.current()
    thread_id = ctx.thread_id if ctx else None
    
    if not thread_id:
        return "Error: No active conversation to search."
    
    try:
        from app.core.memory.backends.sql_short_term import SqlShortTermMemory
        short_term = SqlShortTermMemory()
        
        messages = await short_term.search_messages(query, thread_id, limit=8)
        
        if not messages:
            return f"No messages found matching '{query}' in this conversation."
        
        lines = [f"Found {len(messages)} messages:\n"]
        for msg in messages[:5]:
            role = "User" if msg.type == "human" else "You"
            content = str(msg.content)[:250].replace('\n', ' ')
            lines.append(f"- [{role}]: {content}...")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"[MemoryTool] Search failed: {e}")
        return f"Failed to search: {str(e)}"
