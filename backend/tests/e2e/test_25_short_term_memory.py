"""短期记忆/工作区工具：write_handover_notes 写入共享上下文（无 LLM/DB）。"""

from __future__ import annotations

import pytest

from app.core.context.manager import ContextManager, EvoContext
from app.core.context.schemas import ContextMetadata
from app.core.engine.state import AgentState
from app.core.memory.tools import write_handover_notes

pytestmark = pytest.mark.unit


class TestHandoverNotes:
    async def test_write_handover_notes_saves_to_shared_context(self) -> None:
        state = AgentState(thread_id="t", project_id=0, shared_context={})
        ctx = EvoContext(
            thread_id="t",
            project_id=0,
            member_id=0,
            request_id="r",
            metadata=ContextMetadata(blackboard=state),
        )
        token = ContextManager.set(ctx)
        try:
            result = await write_handover_notes("API: /v1/ptexam", key="ptexam_api")
            assert "Successfully" in result, result
            assert state.shared_context.get("ptexam_api") == "API: /v1/ptexam"
            assert ctx.metadata.shared_context.get("ptexam_api") == "API: /v1/ptexam"
        finally:
            ContextManager.reset(token)

    async def test_write_handover_notes_overwrites_same_key(self) -> None:
        state = AgentState(thread_id="t", project_id=0, shared_context={"k": "old"})
        ctx = EvoContext(
            thread_id="t",
            project_id=0,
            member_id=0,
            request_id="r",
            metadata=ContextMetadata(blackboard=state),
        )
        token = ContextManager.set(ctx)
        try:
            await write_handover_notes("new-value", key="k")
            assert state.shared_context.get("k") == "new-value"
        finally:
            ContextManager.reset(token)
