"""
Memory Tools - Conversation history search.

Note: Long-term memory (remember/recall) has been moved to 
app.core.engine.tools.memory_tools for simplified architecture.
"""
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.context.manager import ContextManager
from app.core.memory import MemoryContainer, MemoryConfig
from app.core.tools import evoloop_tool
from app.utils import ContentFormatter


@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.search_history",
    name_map={"zh": "搜索历史", "en": "Search History"}
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
        limit: Optional. Maximum number of results to return (default 10).
        thread_id: OPTIONAL - DO NOT provide this unless explicitly asked to search 
                   a different conversation. The tool automatically uses the current 
                   session's thread_id when this is left empty.

    Advanced Query Syntax:
        - Space-separated = OR search: "PostgreSQL MySQL" matches either word
        - Use specific technical terms, not vague references
        - Extract 2-3 unique keywords for best results
    
    Examples:
        User: "回到第3轮的方案" → search_history(query="PostgreSQL MySQL")  # extract actual topic
        User: "之前说的错误处理" → search_history(query="exception handler")
        User: "那个Docker配置" → search_history(query="Dockerfile compose")
        User: "找错误或异常" → search_history(query="error exception fail")  # multiple keywords = OR
    """
    if not query:
        return "Error: query is required."
    
    # Get thread_id from context if not provided
    ctx = ContextManager.current()
    target_thread = thread_id or ctx.thread_id

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        results = await manager.search_messages(query, target_thread, limit)
        
        if not results:
            return ContentFormatter.chat_search_results(query, [])
        
        return ContentFormatter.chat_search_results(query, results)
    finally:
        await container.shutdown()


# NOTE: The following long-term memory tools have been consolidated into 
# app.core.engine.tools.memory_tools for a simplified "remember/recall" interface:
# - save_preference → use 'remember' instead
# - add_concept → use 'remember' instead  
# - find_related_episodes → use 'recall' instead
