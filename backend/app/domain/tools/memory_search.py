from typing import Optional
from app.core.memory import memory_manager
from app.core.tools import evoloop_tool
from app.core.context.manager import ContextManager


@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.manage_memory",
    name_map={"zh": "搜索对话历史", "en": "Search Chat History"}
)
async def search_chat_history(query: str, thread_id: Optional[str] = None, limit: int = 10):
    """
    Search the conversation history for specific keywords or topics.
    Useful for recalling past decisions, requirements, or code snippets discussed earlier.

    CRITICAL: This tool automatically searches the CURRENT conversation thread by default.
    You do NOT need to provide thread_id unless you want to search a different conversation.

    WHEN TO USE:
    - User refers to "之前说的" / "刚才讨论的" / "第X轮" / "earlier" / "previously"
    - User asks to "回到" / "参考" / "基于之前的"某个方案或讨论  
    - Current context window (50 recent messages) doesn't contain the referenced info
    - You need to recall requirements, decisions, or code from earlier in THIS conversation

    KEYWORD EXTRACTION STRATEGY (IMPORTANT):
    The search uses SQL LIKE matching (not semantic). Extract CORE CONCEPTS from user's reference:
    
    ❌ BAD:  "第3轮方案" → likely won't match (users don't say "第3轮" in their messages)
    ✅ GOOD:  "PostgreSQL" or "数据库" → extracts the actual topic
    
    ❌ BAD:  "刚才的错误处理" → too vague
    ✅ GOOD:  "try-catch" or "exception" → specific technical terms
    
    Tips:
    1. Extract technical terms, not positional references ("第X轮")
    2. Use multiple specific keywords rather than one long phrase
    3. If first search returns nothing, try synonyms or broader terms
    4. Search for unique terms mentioned in the discussion (file names, function names, etc.)

    Args:
        query: The search term or keywords. Extract core concepts, not positional references.
               GOOD examples: "PostgreSQL", "auth_service", "Dockerfile", "retry逻辑"
               BAD examples: "第3轮", "刚才说的", "之前的方案"
        thread_id: OPTIONAL - DO NOT provide this unless explicitly asked to search 
                   a different conversation. The tool automatically uses the current 
                   session's thread_id when this is left empty.
        limit: Optional. Maximum number of results to return (default 10).

    Examples:
        User: "回到第3轮的方案" → search_chat_history(query="PostgreSQL MySQL")  # extract actual topic
        User: "之前说的错误处理" → search_chat_history(query="exception handler")
        User: "那个Docker配置" → search_chat_history(query="Dockerfile compose")
    """
    # If thread_id is not provided, try to get it from current context
    if not thread_id:
        ctx = ContextManager.current()
        thread_id = ctx.thread_id

    results = await memory_manager.search_messages(query, thread_id, limit)
    
    if not results:
        return f"No results found for '{query}' in the conversation history."

    output = [f"Search results for '{query}':"]
    for msg in results:
        role_label = "User" if msg.type == "human" else "Assistant"
        content_preview = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        output.append(f"[{role_label}]: {content_preview}")

    return "\n\n".join(output)
