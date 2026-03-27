"""
Memory Tools - Individual tools for memory management.

This module provides standalone tools for memory operations,
replacing the monolithic manage_memory facade.
"""
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.context.manager import ContextManager
from app.core.memory import memory_manager
from app.core.tools import evoloop_tool
from app.domain.tools.memory import (
    add_concept_impl,
    find_related_episodes_impl,
    save_preference_impl,
)
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
    
    results = await memory_manager.search_messages(query, target_thread, limit)
    
    if not results:
        return ContentFormatter.chat_search_results(query, [])
    
    return ContentFormatter.chat_search_results(query, results)


@evoloop_tool(
    is_state_mutating=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.save_preference",
    name_map={"zh": "保存偏好", "en": "Save Preference"}
)
async def save_preference(
    key: str,
    value: str,
    description: str = "",
) -> str:
    """
    Save a user preference or instruction to long-term memory.
    
    Use this when the user expresses a preference you should remember
    for future tasks, such as coding style, preferred technologies, etc.
    
    Args:
        key: The preference name/identifier (e.g., "code_style", "preferred_db").
        value: The preference value (e.g., "Use Pydantic v2", "PostgreSQL").
        description: Optional detailed description of the preference.
    
    Example:
        save_preference(
            key="code_style",
            value="Use type hints and Pydantic models",
            description="Always add type annotations to function parameters"
        )
    """
    if not key or not value:
        return "Error: Both 'key' and 'value' are required."
    
    return await save_preference_impl(key=key, value=value, description=description)


@evoloop_tool(
    is_state_mutating=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.add_concept",
    name_map={"zh": "添加概念", "en": "Add Concept"}
)
async def add_concept(
    name: str,
    description: str,
) -> str:
    """
    Add a knowledge concept or term to the Project's Knowledge Graph.
    
    Use this to store important technical concepts, architecture decisions,
    or domain knowledge discovered during the conversation.
    
    Args:
        name: The concept name (e.g., "Auth Flow", "Database Schema").
        description: Detailed description of the concept.
    
    Example:
        add_concept(
            name="JWT Authentication",
            description="Uses JWT tokens with 15-minute expiry, refresh tokens valid for 7 days"
        )
    """
    if not name or not description:
        return "Error: Both 'name' and 'description' are required."
    
    return await add_concept_impl(name=name, description=description)


@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.find_related_episodes",
    name_map={"zh": "查找相关历史", "en": "Find Related Episodes"}
)
async def find_related_episodes(
    concept_name: str,
) -> str:
    """
    Find historical tasks related to a concept.
    
    Use this to discover past work, decisions, or discussions related to
    a specific concept in the project's knowledge graph.
    
    Args:
        concept_name: The concept name to search for related episodes.
    
    Example:
        find_related_episodes(concept_name="Authentication")
    """
    if not concept_name:
        return "Error: 'concept_name' is required."
    
    return await find_related_episodes_impl(concept_name=concept_name)


# NOTE: The following functions are available in memory.py but not exposed as standalone tools
# to keep the tool set focused. They can be added later if needed:
# - get_user_preferences_impl: Retrieve all user preferences
# - search_concepts_impl: Search the project's Concept Graph
