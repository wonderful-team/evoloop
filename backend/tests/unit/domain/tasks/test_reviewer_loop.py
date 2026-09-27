"""Reviewer loop unit tests: task_no assignment, review flow, 2-round cap."""

from __future__ import annotations

import json as _json
from types import SimpleNamespace

import pytest

from app.domain.tasks.review import resolve_review_verdict
from app.domain.tasks.service import TaskQueueService


@pytest.mark.asyncio
async def test_task_no_increments_per_project(_db):
    t1 = await TaskQueueService.create_task(
        project_id=1, title="a", description="d"
    )
    t2 = await TaskQueueService.create_task(
        project_id=1, title="b", description="d"
    )
    t3 = await TaskQueueService.create_task(
        project_id=2, title="c", description="d"
    )
    assert t2.task_no == ((t1.task_no or 0) + 1)
    assert t3.task_no == 1


@pytest.mark.asyncio
async def test_t4_with_origin_waits_for_review(_db, monkeypatch):
    """T3/T4 with origin thread: no system:auto — waiting_acceptance+review."""
    dispatched: list[dict] = []

    import app.core.engine.dispatch as dispatch_mod

    async def _fake_dispatch(thread_id, message_content, **kw):
        dispatched.append({"thread_id": thread_id, "content": message_content[:2000], **kw})
        return SimpleNamespace(
            status=SimpleNamespace(FAILED=False), inputs={"x": 1}, error=None
        )

    monkeypatch.setattr(dispatch_mod, "dispatch_agent_run", _fake_dispatch)
    import app.domain.tasks.review as review_mod

    monkeypatch.setattr(review_mod, "dispatch_agent_run", _fake_dispatch, raising=False)

    task = await TaskQueueService.create_task(
        project_id=1,
        title="reviewed task",
        description="do it",
        source="user",
        source_ref={"kind": "message", "ref": "conv-1"},
        risk_level="T3",
    )
    await TaskQueueService.take_task(task.id, "wakeup_1_test")
    await TaskQueueService.advance_task(
        task.id, "self_checked", result="done", self_check=None
    )

    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "waiting_acceptance"
    assert fresh.review_pending is True
    assert fresh.acceptance is None  # no system:auto receipt
    assert fresh.last_thread_id.startswith("wakeup_") or fresh.last_thread_id


@pytest.mark.asyncio
async def test_t34_without_origin_autocompletes(_db):
    """No origin thread (board task): system:auto completed as before."""
    task = await TaskQueueService.create_task(
        project_id=1, title="board task", description="d", risk_level="T3"
    )
    await TaskQueueService.take_task(task.id, "wakeup_2_x")
    await TaskQueueService.advance_task(task.id, "self_checked", result="ok")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "completed"
    assert (fresh.acceptance or {}).get("by") == "system:auto"




def _patch_dispatch(monkeypatch, sink=None):
    """Never launch a real reviewer run; optionally collect messages."""
    import app.domain.tasks.review as review_mod

    async def _fake_dispatch(thread_id, message_content=None, **_kw):  # noqa: ARG001
        if sink is not None:
            sink.append(message_content)
        return SimpleNamespace(
            status=SimpleNamespace(FAILED=False), inputs=None, error=None
        )

    monkeypatch.setattr(review_mod, "dispatch_agent_run", _fake_dispatch)


@pytest.mark.asyncio
async def test_review_verdict_accepts(_db, monkeypatch):
    _patch_dispatch(monkeypatch)
    task = await TaskQueueService.create_task(
        project_id=1,
        title="t",
        description="d",
        risk_level="T3",
        source="user",
        source_ref={"kind": "message", "ref": "conv-9"},
    )
    await TaskQueueService.take_task(task.id, "wakeup_3_x")
    await TaskQueueService.advance_task(task.id, "self_checked", result="ok")
    await resolve_review_verdict(task.id, "复查完成。目标达成。\n结论：通过")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "completed"
    assert (fresh.acceptance or {}).get("by") == "reviewer:auto"


@pytest.mark.asyncio
async def test_review_two_rounds_then_failed_arbitration(_db, monkeypatch):
    """2 reviewer rejections → failed + escalation (no infinite rework)."""
    sent: list[str] = []
    _patch_dispatch(monkeypatch, sink=sent)

    task = await TaskQueueService.create_task(
        project_id=1,
        title="t",
        description="d",
        risk_level="T3",
        source="user",
        source_ref={"kind": "message", "ref": "conv-2"},
    )
    await TaskQueueService.take_task(task.id, "wakeup_4_x")
    await TaskQueueService.advance_task(task.id, "self_checked", result="ok")

    # 第 1 轮：评审不通过 → 回队 pending（review_count=1）
    await resolve_review_verdict(task.id, "结论：不通过：漏了第 3 步")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "pending"
    assert fresh.review_count == 1
    assert "漏了第 3 步" in ((fresh.acceptance or {}).get("feedback") or "")

    # 重跑 → 再次完成 → 再次评审 → 第 2 轮仍不通过 → failed（转人工）
    await TaskQueueService.take_task(task.id, "wakeup_4_y")
    await TaskQueueService.advance_task(task.id, "self_checked", result="ok2")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "waiting_acceptance"
    await resolve_review_verdict(task.id, "结论：不通过：仍缺第 3 步")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "failed"
    assert fresh.review_count == 2
    assert (fresh.acceptance or {}).get("escalated") is True
    assert len(sent) >= 1  # arbitration message dispatched to origin


@pytest.mark.asyncio
async def test_review_no_verdict_line_counts_as_rejection(_db, monkeypatch):
    _patch_dispatch(monkeypatch)
    task = await TaskQueueService.create_task(
        project_id=1,
        title="t",
        description="d",
        risk_level="T3",
        source="user",
        source_ref={"kind": "message", "ref": "conv-7"},
    )
    await TaskQueueService.take_task(task.id, "wakeup_5_x")
    await TaskQueueService.advance_task(task.id, "self_checked", result="ok")
    await resolve_review_verdict(task.id, "我觉得大概可以吧，不错。")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "pending"
    assert fresh.review_count == 1


@pytest.mark.asyncio
async def test_human_rejection_not_capped(_db):
    """用户拒绝不受 2 轮上限约束（T2 waiting_acceptance 人工路径）。"""
    task = await TaskQueueService.create_task(
        project_id=1, title="t", description="d", risk_level="T2"
    )
    await TaskQueueService.take_task(task.id, "wakeup_6_x")
    await TaskQueueService.advance_task(task.id, "self_checked", result="ok")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "waiting_acceptance"
    for i in range(3):
        await TaskQueueService.submit_acceptance(
            task.id, by="user", verdict="rejected", feedback=f"no-{i}"
        )
        fresh = await TaskQueueService.get_task(task.id)
        assert fresh.status == "pending"
        assert fresh.review_count == 0
        await TaskQueueService.take_task(task.id, f"wakeup_6_r{i}")
        await TaskQueueService.advance_task(task.id, "self_checked", result="ok")


@pytest.mark.asyncio
async def test_facade_create_returns_task_no(_db, monkeypatch):
    from app.core.context.manager import ContextManager
    from app.domain.tasks.tools import tasks

    monkeypatch.setattr(
        ContextManager,
        "current",
        lambda: SimpleNamespace(project_id=1),
    )
    out = await tasks(
        action="create",
        title="numbered",
        source="user",
        config={"configurable": {"thread_id": "conv-11"}},
    )
    data = _json.loads(out)
    assert data["task_no"] is not None
    task = await TaskQueueService.get_task(data["id"])
    assert task.origin_thread_id == "conv-11"


@pytest.mark.asyncio
async def test_review_dispatch_failure_keeps_waiting_acceptance(_db, monkeypatch):
    """评审派发失败 → 保持 waiting_acceptance（绝不 fallback 自动验收）。

    旧实现：回灌失败 → submit_acceptance(accepted)——执行者结果因基础设施
    故障"自我验收"，绕过评审闸门。新契约：保持现状，由 reconciler 的
    30min 评审超时兜底收敛（空结论=不通过 → 2 轮上限）。
    """
    import app.domain.tasks.review as review_mod

    async def _failing_dispatch(*_a, **_kw):
        return SimpleNamespace(
            status=SimpleNamespace(FAILED=True), inputs=None, error="origin thread gone"
        )

    monkeypatch.setattr(review_mod, "dispatch_agent_run", _failing_dispatch)

    task = await TaskQueueService.create_task(
        project_id=1,
        title="t",
        description="d",
        risk_level="T3",
        source="user",
        source_ref={"kind": "message", "ref": "conv-77"},
    )
    await TaskQueueService.take_task(task.id, "wakeup_77_x")
    # advance → self_checked → waiting_acceptance + review_requested → trigger_review
    updated = await TaskQueueService.advance_task(task.id, "self_checked", result="ok")

    fresh = await TaskQueueService.get_task(task.id)
    assert updated.status == "waiting_acceptance"
    assert fresh.status == "waiting_acceptance"  # 不被自动验收
    assert fresh.acceptance is None  # 无验收回执落库
    assert fresh.review_pending is True  # 评审标记保留，等超时兜底


@pytest.mark.asyncio
async def test_review_references_and_audit_prompt(_db, monkeypatch):
    """验证评审双层解耦：UI 引用化 + Prompt 产物清单与只读核验指令。"""
    from app.infrastructure.database.sql.database import session_scope
    from app.models.conversation import Message
    from app.models.task_workflow import TaskArtifact

    dispatched_calls: list[dict] = []
    import app.domain.tasks.review as review_mod

    async def _capture_dispatch(thread_id, message_content, references=None, **kw):
        dispatched_calls.append({
            "thread_id": thread_id,
            "content": message_content,
            "references": references,
            **kw,
        })
        return SimpleNamespace(
            status=SimpleNamespace(FAILED=False), inputs={"captured": True}, error=None
        )

    monkeypatch.setattr(review_mod, "dispatch_agent_run", _capture_dispatch)

    task = await TaskQueueService.create_task(
        project_id=1,
        title="跨境电商选品调研",
        description="分析Q4爆款并生成选品调研报告",
        risk_level="T3",
        source="user",
        source_ref={"kind": "message", "ref": "conv-user-main"},
        acceptance_criteria=["包含至少3个候选类目", "有明确的利润率测算"],
    )
    executor_thread = f"wakeup_1_{task.id}"
    await TaskQueueService.take_task(task.id, executor_thread)

    # 模拟执行线程产生 AI 回复和真实产物
    async with session_scope() as session:
        msg = Message(
            id="msg-exec-1",
            thread_id=executor_thread,
            role="ai",
            category="assistant_response",
            content="选品调研已完成，已输出报告至 /workspace/reports/q4_products.md",
            sequence_number=1,
        )
        session.add(msg)
        art = TaskArtifact(
            id="art-1",
            project_id=1,
            workflow_id="wf-1",
            task_id=task.id,
            stage="market_research",
            artifact_type="markdown",
            summary="Q4 爆款选品调研报告",
            data={"file_path": "/workspace/reports/q4_products.md", "name": "Q4选品报告.md"},
        )
        session.add(art)

    # 执行者提交自检结论
    await TaskQueueService.advance_task(
        task.id,
        "self_checked",
        result="已完成3个候选类目的调研与测算",
    )

    # 验证评审派发情况
    assert len(dispatched_calls) == 1
    call = dispatched_calls[0]
    assert call["thread_id"] == "conv-user-main"

    # 1. 结构化 References 校验 (UI 呈现层)
    refs = call["references"]
    assert refs is not None
    ref_types = [r["type"] for r in refs]
    assert "message" in ref_types
    assert "file" in ref_types
    file_ref = next(r for r in refs if r["type"] == "file")
    assert file_ref["target_id"] == "/workspace/reports/q4_products.md"
    assert file_ref["name"] == "Q4选品报告.md"

    # 2. Prompt 纯净化与审计指令校验 (LLM 模型审计层)
    prompt = call["content"]
    assert "【执行交付简报】" in prompt
    assert "已完成3个候选类目的调研与测算" in prompt
    assert "包含至少3个候选类目" in prompt  # acceptance criteria
    assert "/workspace/reports/q4_products.md" in prompt  # 交付物清单
    assert "view_file" in prompt  # 明确指示使用只读工具核查真实文件
    assert len(prompt) < 1000  # 告别 4000 字长文刷屏

    # 3. 评审结论通过流转
    await resolve_review_verdict(task.id, "已通过 view_file 检查选品报告，数据完整。\n结论：通过")
    fresh = await TaskQueueService.get_task(task.id)
    assert fresh.status == "completed"
    assert fresh.acceptance["verdict"] == "accepted"
    assert fresh.acceptance["by"] == "reviewer:auto"

