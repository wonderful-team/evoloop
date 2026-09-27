"""Integration: multi_choice 请求全链路 (real SQLite).

覆盖收编后的完整闭环：
1. ``create_request(request_type="multi_choice")`` 真实落库（type/options/status）。
2. ``normalize_hitl_input`` 把逗号分隔的多选结果原样归一化（free-text 语义）。
3. ``finalize_request`` 批准后把结果写入 ``human_requests.result``。
"""

import pytest

from app.core.hitl.core import create_request, finalize_request
from app.core.hitl.orchestrator import normalize_hitl_input


@pytest.fixture
def hitl_scope(test_session_scope, monkeypatch):
    """把 hitl.core 的 session_scope 指向测试 SQLite，返回该会话作用域。"""
    import app.core.hitl.core as core_mod

    monkeypatch.setattr(core_mod, "session_scope", test_session_scope)
    return test_session_scope


@pytest.mark.asyncio
async def test_multi_choice_create_persists_type_and_options(hitl_scope):
    from app.models.conversation import HumanRequest

    req = await create_request(
        "t-mc-1",
        "multi_choice",
        "请勾选要处理的退款工单",
        options=["全部", "仅待转账", "仅申请售后", "暂不处理"],
    )
    assert req.request_type == "multi_choice"

    async with hitl_scope() as db:
        row = await db.get(HumanRequest, req.id)
        assert row is not None
        assert row.type == "multi_choice"
        assert row.options == ["全部", "仅待转账", "仅申请售后", "暂不处理"]
        assert row.status == "pending"


@pytest.mark.asyncio
async def test_multi_choice_resume_normalize_and_finalize(hitl_scope):
    from app.models.conversation import HumanRequest

    req = await create_request(
        "t-mc-2", "multi_choice", "请勾选", options=["A", "B", "C"]
    )

    # 运营勾选了多项 → 逗号分隔回传 → 原样归一化
    normalized = normalize_hitl_input(
        {"request_type": "multi_choice", "id": req.id, "name": "ask_human", "args": {}},
        "A,C",
    )
    assert normalized == "A,C"

    # finalize 把结果落库
    ok = await finalize_request(
        "t-mc-2", req.id, "call-mc-2", "completed", response=normalized
    )
    assert ok is True

    async with hitl_scope() as db:
        row = await db.get(HumanRequest, req.id)
        assert row.status == "completed"
        assert row.result == "A,C"


def test_multi_choice_does_not_coerce_yes():
    """multi_choice 里 "yes" 是合法选项文本，不得归一化成 APPROVED。"""
    normalized = normalize_hitl_input(
        {"request_type": "multi_choice"}, "yes"
    )
    assert normalized == "yes"
