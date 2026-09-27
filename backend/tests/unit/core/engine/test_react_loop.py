"""React main-loop orchestration tests — no DB, no real LLM.

Covers ``run_agent_loop`` assembly, doom-loop deterministic finish, state
write-back and the completion-pipeline hook, plus ``_extract_summary``.
"""


import pytest

from app.core.engine.message.native_classes import HumanMessage
from app.core.engine.state import AgentState


def _config(**overrides):
    cfg = {
        "configurable": {"thread_id": "t1", "model": "doubao-seed", "run_id": "r1"},
        "metadata": {"source": "web"},
    }
    cfg.update(overrides)
    return cfg


def _state() -> AgentState:
    return AgentState(
        messages=[HumanMessage(content="你好")],
        tool_history=[],
        thread_id="t1",
        project_id=7,
    )


@pytest.mark.asyncio



async def run_agent_loop_under_test(state, config, **kwargs):
    from app.core.engine.react.loop import run_agent_loop

    return await run_agent_loop(state, config, "t1", **kwargs)
