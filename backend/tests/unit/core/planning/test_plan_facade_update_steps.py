"""plan facade update_steps 批量语义：预检强校验 + 多项一次应用 + 逐项事件。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.core.planning.facade_tool import plan


class _FakeStep:
    def __init__(self, sid: str):
        self.id = sid
        self.status = "pending"
        self.result = None


@pytest.fixture
def _fake_steps(monkeypatch):
    steps = {"s1": _FakeStep("s1"), "s2": _FakeStep("s2")}

    class _FakeBus:
        def __init__(self):
            self.published = []

        async def publish(self, event):
            self.published.append(event)

    bus = _FakeBus()

    @asynccontextmanager
    async def _scope():
        async def _execute(_stmt):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: list(steps.values()))
            )

        yield SimpleNamespace(
            execute=_execute, add=lambda _o: None, commit=lambda: None
        )

    monkeypatch.setattr("app.core.planning.facade_tool.session_scope", _scope)
    monkeypatch.setattr("app.core.events.system_bus", bus)
    return steps, bus.published


def _config():
    return {"configurable": {"thread_id": "t-1"}, "metadata": {"run_id": "r-1"}}


class TestCreateStepNormalization:
    async def test_dict_steps_are_normalized_for_storage(self, monkeypatch):
        added = []

        @asynccontextmanager
        async def _scope():
            async def _execute(_stmt):
                return SimpleNamespace(scalar_one_or_none=lambda: None)

            yield SimpleNamespace(execute=_execute, add=added.append)

        monkeypatch.setattr("app.core.planning.facade_tool.session_scope", _scope)
        output = await plan(
            action="create",
            title="设备排查",
            steps=[{"title": "查询设备", "description": "读取设备与宏信息"}],
            config=_config(),
        )

        assert not output.startswith("Error:")
        step = added[1]
        assert step.title == "查询设备"
        assert step.description == "读取设备与宏信息"

    async def test_invalid_step_shape_is_rejected(self, monkeypatch):
        @asynccontextmanager
        async def _scope():
            yield SimpleNamespace(add=lambda _object: None)

        monkeypatch.setattr("app.core.planning.facade_tool.session_scope", _scope)
        output = await plan(
            action="create",
            title="设备排查",
            steps=[123],
            config=_config(),
        )

        assert output.startswith("Error:")


class TestUpdateStepsPreflight:
    async def test_empty_steps_rejected(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps", plan_id="p1", steps=[], config=_config()
        )
        assert out.startswith("Error:")
        assert "steps" in out
        assert steps["s1"].status == "pending"
        assert events == []

    async def test_non_dict_item_rejected(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=["s1"],
            config=_config(),
        )
        assert out.startswith("Error:")
        assert "必须是对象" in out
        assert steps["s1"].status == "pending"
        assert events == []

    async def test_missing_step_id_rejected(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[{"status": "completed", "result": "x"}],
            config=_config(),
        )
        assert out.startswith("Error:")
        assert "step_id" in out
        assert steps["s1"].status == "pending"
        assert events == []

    async def test_unknown_step_id_rejected_atomically(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[
                {"step_id": "s1", "status": "completed", "result": "ok"},
                {"step_id": "ghost", "status": "pending"},
            ],
            config=_config(),
        )
        assert out.startswith("Error:")
        assert "ghost" in out
        assert steps["s1"].status == "pending"
        assert events == []


class TestUpdateStepsResultValidation:
    async def test_completed_without_result_rejected(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[{"step_id": "s1", "status": "completed", "result": ""}],
            config=_config(),
        )
        assert out.startswith("Error:")
        assert "result" in out
        assert steps["s1"].status == "pending"
        assert events == []

    async def test_completed_with_whitespace_result_rejected(self, _fake_steps):
        steps, _ = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[{"step_id": "s1", "status": "completed", "result": "   "}],
            config=_config(),
        )
        assert out.startswith("Error:")
        assert steps["s1"].status == "pending"

    async def test_completed_with_result_accepted(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[
                {
                    "step_id": "s1",
                    "status": "completed",
                    "result": "查完库存，缺货商品已下架",
                }
            ],
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert steps["s1"].status == "completed"
        assert steps["s1"].result == "查完库存，缺货商品已下架"
        assert len(events) == 1
        assert events[0].step_id == "s1"
        assert events[0].status == "completed"
        assert events[0].plan_id == "p1"
        assert events[0].thread_id == "t-1"

    async def test_long_result_truncated(self, _fake_steps):
        steps, _ = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[{"step_id": "s1", "status": "completed", "result": "x" * 800}],
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert len(steps["s1"].result) == 500

    async def test_in_progress_without_result_still_allowed(self, _fake_steps):
        steps, _ = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[{"step_id": "s1", "status": "in_progress", "result": ""}],
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert steps["s1"].status == "in_progress"


class TestUpdateStepsBatch:
    async def test_batch_mixed_statuses_applied_and_events_per_step(self, _fake_steps):
        steps, events = _fake_steps
        out = await plan(
            action="update_steps",
            plan_id="p1",
            steps=[
                {"step_id": "s1", "status": "completed", "result": "第一步完成"},
                {"step_id": "s2", "status": "in_progress"},
            ],
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert steps["s1"].status == "completed"
        assert steps["s1"].result == "第一步完成"
        assert steps["s2"].status == "in_progress"
        assert [(e.step_id, e.status) for e in events] == [
            ("s1", "completed"),
            ("s2", "in_progress"),
        ]

    async def test_batch_keeps_other_steps_untouched(self, _fake_steps):
        steps, _ = _fake_steps
        await plan(
            action="update_steps",
            plan_id="p1",
            steps=[{"step_id": "s2", "status": "failed", "result": "设备不在线"}],
            config=_config(),
        )
        assert steps["s2"].status == "failed"
        assert steps["s1"].status == "pending"
        assert steps["s1"].result is None
