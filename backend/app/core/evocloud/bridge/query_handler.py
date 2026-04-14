# query_handler.py - 处理来自 Mobile (via Gateway) 的查询请求

import logging
from typing import Any

from sqlalchemy import select

from app.core.evocloud.schemas import (
    ConversationQueryItem,
    McpServerInfo,
    MessageQueryItem,
    ModelInfo,
)
from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation, Message

logger = logging.getLogger(__name__)


async def handle_query_request(query_type: str, thread_id: str, params: dict[str, Any]) -> Any:
    """
    处理来自 Gateway 的查询请求
    
    Args:
        query_type: 查询类型 (conversations, history, skills, mcp_servers, models)
        thread_id: 对话线程 ID (可选)
        params: 查询参数
    
    Returns:
        查询结果
    """
    logger.debug(f"[QueryHandler] {query_type} (thread={thread_id}, params={params})")

    try:
        if query_type == "conversations":
            return await _query_conversations(params)
        elif query_type == "history":
            return await _query_history(thread_id, params)
        elif query_type == "skills":
            return await _query_skills(params)
        elif query_type == "mcp_servers":
            return await _query_mcp_servers(params)
        elif query_type == "models":
            return await _query_models(params)
        else:
            return {"error": f"Unknown query type: {query_type}"}
    except Exception as e:
        logger.error(f"[QueryHandler] Error handling {query_type}: {e}")
        return {"error": str(e)}


async def _query_conversations(params: dict[str, Any]) -> list[ConversationQueryItem]:
    """查询对话列表"""
    try:
        project_id = params.get("project_id")

        async with get_db_session() as db:
            stmt = select(Conversation).order_by(Conversation.updated_at.desc())
            if project_id is not None:
                stmt = stmt.where(Conversation.project_id == project_id)
            result = await db.execute(stmt)
            conversations = result.scalars().all()
            return [
                ConversationQueryItem(
                    id=str(c.id),
                    title=c.title,
                    project_id=c.project_id,
                    created_at=c.created_at.isoformat() if c.created_at else None,
                    updated_at=c.updated_at.isoformat() if c.updated_at else None,
                )
                for c in conversations
            ]
    except Exception as e:
        logger.error(f"[QueryHandler] Failed to query conversations: {e}")
        return []


async def _query_history(thread_id: str, params: dict[str, Any]) -> list[MessageQueryItem] | dict[str, str]:
    """查询对话历史"""
    if not thread_id:
        return {"error": "thread_id required"}

    try:
        limit = int(params.get("limit", 50))

        async with get_db_session() as db:
            stmt = (
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()
            return [
                MessageQueryItem(
                    id=str(m.id),
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at.isoformat() if m.created_at else None,
                )
                for m in messages
            ]
    except Exception as e:
        logger.error(f"[QueryHandler] Failed to query history: {e}")
        return []


async def _query_skills(params: dict[str, Any]) -> list[Any]:
    """查询技能列表"""
    # TODO: 从 SkillManager 获取
    return []


async def _query_mcp_servers(params: dict[str, Any]) -> list[McpServerInfo]:
    """查询 MCP 服务器列表"""
    try:
        from app.core.mcp.client import mcp_client_manager

        servers = []
        for name, server in mcp_client_manager._servers.items():
            servers.append(McpServerInfo(
                name=name,
                type=server.type.value if hasattr(server.type, 'value') else str(server.type),
                connected=server.connected,
            ))
        return servers
    except Exception as e:
        logger.error(f"[QueryHandler] Failed to query MCP servers: {e}")
        return []


async def _query_models(params: dict[str, Any]) -> list[ModelInfo]:
    """查询可用模型列表"""
    from app.infrastructure.llm.platform_service import get_available_llm_models

    models = []
    raw_models = await get_available_llm_models()
    for m in raw_models:
        model_id = m.get("model_id", "")
        display_name = m.get("display_name", model_id)
        models.append(ModelInfo(id=model_id, name=display_name))
    return models
