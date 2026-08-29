"""Agent engine 侧 HITL 运行时实现（EngineRuntime 协议）。

hitl 编排层的 engine 反向依赖（MessageHandler / Repository / Publisher /
AgentToolExecutor / AgentState）全部收敛于此。模块顶层自注册，hitl 侧只通过
``app.core.hitl.engine_runtime`` 协议调用，不再反向引用 ``app.core.engine.*``
——依赖方向归位为 engine → hitl（合法方向）。
"""

import asyncio
import logging
from typing import Any

from app.core.context.manager import ContextManager
from app.core.engine.message.factory import MessageBlockFactory
from app.core.engine.message.handler import MessageHandler
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.repository import MessageRepository
from app.core.engine.state import AgentState
from app.core.engine.tools.executor import AgentToolExecutor
from app.core.hitl.engine_runtime import register_engine_runtime
from app.core.hitl.types import HITLRequestStatus
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


class HitlEngineRuntime:
    def push_hitl_request(
        self,
        *,
        thread_id: str,
        project_id: int | None,
        run_id: str | None,
        request_type: str,
        prompt: str,
        request_id: str,
        options: list[str] | None,
        context: str | None,
        default_value: str | None,
        tool_call_id: str | None,
        tool_name: str,
        parent_id: str | None,
        metadata: dict | None,
    ) -> None:
        """推送到当前会话渠道：subagent 透传判断 + MessageHandler 后台任务。"""
        ctx = ContextManager.current()
        suppress_user_push = bool(
            ctx and (ctx.metadata or {}).get("task_type") == "subagent"
        )
        handler = MessageHandler(
            thread_id=thread_id,
            project_id=project_id,
            run_id=run_id,
        )
        asyncio.create_task(
            handler.handle_hitl_request(
                request_type=request_type,
                prompt=prompt,
                request_id=request_id,
                options=options,
                context=context,
                default_value=default_value,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                parent_id=parent_id,
                metadata=metadata,
                suppress_user_push=suppress_user_push,
            )
        )

    async def close_hitl_message(
        self, thread_id: str, tool_call_id: str, status: str
    ) -> bool:
        repo = MessageRepository(thread_id=thread_id)
        return await repo.update_status_by_tool_call_id(tool_call_id, status)

    async def persist_hitl_user_message(
        self,
        thread_id: str,
        project_id: int | None,
        member_id: int,
        tool_call_id: str,
        user_content: str | None,
        final_result: str,
    ) -> None:
        """落 human 消息（用户可见）+ 实时推送 + 更新原 tool 消息结果。"""
        repo = MessageRepository(thread_id, project_id, member_id=member_id)
        if user_content:
            msg_id, seq = await repo.persist(
                role="human",
                content=user_content,
                category="user",
                action_type="text",
                status=HITLRequestStatus.COMPLETED.value,
            )
            if msg_id:
                block = MessageBlockFactory.from_event(
                    thread_id=thread_id,
                    sequence_number=seq,
                    role="human",
                    content=user_content,
                    category="user",
                    status=HITLRequestStatus.COMPLETED.value,
                    message_id=msg_id,
                )
                publisher = MessagePublisher(
                    thread_id=thread_id, project_id=project_id
                )
                await publisher.publish(block)
        await repo.update_tool_result_by_tool_call_id(tool_call_id, final_result)

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict,
        tool_call_id: str,
        config: dict,
        state: Any = None,
    ) -> str:
        """构造 state（缺失时）并重执行授权门控工具，返回结果文本。"""
        if state is None:
            project_id = config.get("metadata", {}).get("project_id") or 0
            state = AgentState(
                thread_id=config.get("configurable", {}).get("thread_id"),
                project_id=project_id,
            )
        tool_map = {
            t.name: t for t in await tool_manager.get_node_tools("worker", state)
        }
        executor = AgentToolExecutor(
            tool_map=tool_map,
            state=state,
            config=config,
            name="HITLResume",
        )
        result = await executor.execute_tool(tool_name, tool_args, tool_call_id, [])
        return result.message.content or ""


def register() -> None:
    """装配本实现（幂等）；模块 import 时自动执行一次。

    供 ``engine_runtime.get_runtime()`` 在"模块已缓存、副作用未重跑"的
    场景（测试 reset 后）显式重放。
    """
    register_engine_runtime(HitlEngineRuntime())


register()
