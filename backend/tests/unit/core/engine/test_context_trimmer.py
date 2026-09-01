"""ContextTrimmer unit tests — budget, token windowing, repair."""


from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.message.native_classes import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
from app.infrastructure.schemas import PlatformModel


def _patch_profile(monkeypatch, *, context_window: int = 2000):
    profile = PlatformModel(
        model_id="m",
        display_name="m",
        provider_name="openai",
        provider_type="openai",
        context_window=context_window,
        max_tokens=1024,
    )
    monkeypatch.setattr(
        "app.core.engine.context_trimmer.llm_platform_service.get_profile",
        lambda _m: profile,
    )


def _mk(n: int, size: int = 100) -> list:
    msgs = []
    for i in range(n):
        msgs.append(HumanMessage(content=f"{i} " + "y" * size))
    return msgs


def test_compute_budget_uses_react_ratio(monkeypatch):
    _patch_profile(monkeypatch, context_window=10_000)
    from app.core.engine.constants import HARD_LIMIT_RATIO
    from app.core.engine.context_trimmer import REACT_BUDGET_RATIO, _compute_budget

    eff, hard = _compute_budget("m")
    assert eff == int(10_000 * REACT_BUDGET_RATIO)
    assert hard == int(10_000 * HARD_LIMIT_RATIO)


def test_trim_short_circuits_under_threshold(monkeypatch):
    _patch_profile(monkeypatch)
    msgs = _mk(3)  # 3 * ~29 tok ≈ 87 < 840 threshold
    t = ContextTrimmer()
    result = t.trim(msgs, model="m", stages={"window"})
    assert result.trigger == TrimTrigger.NONE
    assert result.messages == msgs


def test_trim_window_drops_oldest_keeps_recent(monkeypatch):
    _patch_profile(monkeypatch, context_window=2000)
    msgs = _mk(60, size=100)  # 60 * ~29 ≈ 1740 tok > 840 threshold
    t = ContextTrimmer()
    result = t.trim(msgs, model="m", stages={"window"})
    assert len(result.messages) < len(msgs)
    assert result.trigger == TrimTrigger.TOKEN_BUDGET
    # 最近消息保留
    assert result.messages[-1].content == msgs[-1].content


def test_trim_with_tool_messages_and_repair(monkeypatch):
    _patch_profile(monkeypatch, context_window=2000)
    msgs = [HumanMessage(content=f"h{i} " + "x" * 100) for i in range(40)]
    for i in range(30):
        msgs.append(ToolMessage(content=f"tool out {i} " + "x" * 100, tool_call_id=f"c{i}", name="bash"))
    msgs.append(AIMessage(content="final " + "x" * 100))
    t = ContextTrimmer()
    result = t.trim(msgs, model="m", stages={"window", "repair"})
    # repair 不炸 + 窗口生效
    assert result.messages
    assert result.after_tokens <= result.before_tokens


def test_trim_repair_stage_normalizes_messages(monkeypatch):
    _patch_profile(monkeypatch, context_window=2000)
    msgs = _mk(5)
    t = ContextTrimmer()
    result = t.trim(msgs, model="m", stages={"repair"})
    assert result.messages  # 合法消息 repair 后仍存在


def test_trim_truncated_reports_reduced_tokens(monkeypatch):
    _patch_profile(monkeypatch, context_window=2000)
    msgs = _mk(60)
    t = ContextTrimmer()
    result = t.trim(msgs, model="m", stages={"window"})
    assert result.after_tokens <= result.before_tokens
    assert result.removed_count >= 0
