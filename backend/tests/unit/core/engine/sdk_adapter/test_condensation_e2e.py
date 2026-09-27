"""Condensation 端到端回归（整合缺口复盘产物）。

Agent spec 漏配 condenser 曾导致长对话必然撞 context window 且无自愈
（legacy ContextTrimmer 已删，压缩职责由 SDK condenser 承担）。本测试用
小 max_size + MockLLM 快速触发压缩，锁定三条契约：
1. 超限后 Condensation 事件产生（压缩真的发生）
2. EventLog 总量被控制（不是无限增长）
3. 压缩后后续轮次照常工作
"""

from __future__ import annotations

import pytest
from openhands.sdk import Agent, Conversation, LLM, Message, TextContent
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.sdk.event import Condensation

from app.core.engine.sdk_adapter.mock_llm import install, uninstall


@pytest.fixture
def mock_llm_installed():
    install()
    yield
    uninstall()


def _build_conversation(max_size: int, workspace: str) -> Conversation:
    llm = LLM(
        model="openai/mock-llm",
        api_key="mock",
        base_url="http://127.0.0.1:9",
        stream=True,
    )
    agent = Agent(
        llm=llm,
        tools=[],
        system_prompt="test agent",
        include_default_tools=[],
        condenser=LLMSummarizingCondenser(
            llm=llm, max_size=max_size, keep_first=2
        ),
    )
    return Conversation(agent=agent, workspace=workspace, visualizer=None)


@pytest.mark.timeout(120)
def test_condensation_triggers_and_bounds_event_log(tmp_path, mock_llm_installed):
    conv = _build_conversation(max_size=12, workspace=str(tmp_path / "ws"))
    conv.run()  # 初始化（加载 agent/tools）

    condensation_rounds: list[int] = []
    for i in range(12):
        conv.send_message(
            Message(role="user", content=[TextContent(text=f"round {i} hello")])
        )
        conv.run()
        conds = [e for e in conv.state.events if isinstance(e, Condensation)]
        if conds and not condensation_rounds:
            condensation_rounds.append(i)

    assert condensation_rounds, "12 轮对话（max_size=12）必须至少触发一次压缩"
    assert len(conv.state.events) < 12 * 5, "EventLog 必须被压缩控制（无压缩约 60+）"

    # 压缩后后续轮次照常工作：再发一条，run 正常完成且有回复
    conv.send_message(
        Message(role="user", content=[TextContent(text="post-condensation turn")])
    )
    conv.run()
    last_ai = [
        e
        for e in conv.state.events
        if getattr(e, "source", "") == "agent" and getattr(e, "llm_message", None)
    ]
    assert last_ai, "压缩后新轮次必须有 Agent 回复"
