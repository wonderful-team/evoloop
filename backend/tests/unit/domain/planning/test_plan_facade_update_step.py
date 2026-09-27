"""plan facade update_step 强校验：completed 必填 result + 超长截断。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.domain.planning.facade_tool import plan


class _FakeStep:
    def __init__(self):
        self.status = "pending"
        self.result = None


@pytest.fixture
def _fake_session(monkeypatch):
    step = _FakeStep()
    captured = {}

    @asynccontextmanager
    async def _scope():
        session = SimpleNamespace(
            get=_fake_get,
            add=lambda o: None,
            commit=lambda: None,
        )
        yield session

    async def _fake_get(_model, _id):
        captured["get_called"] = True
        return step

    monkeypatch.setattr(
        "app.domain.planning.facade_tool.session_scope", _scope
    )
    return step, captured


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

        monkeypatch.setattr("app.domain.planning.facade_tool.session_scope", _scope)
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

        monkeypatch.setattr("app.domain.planning.facade_tool.session_scope", _scope)
        output = await plan(
            action="create",
            title="设备排查",
            steps=[123],
            config=_config(),
        )

        assert output.startswith("Error:")


class TestUpdateStepResultValidation:
    async def test_completed_without_result_rejected(self, _fake_session):
        step, _ = _fake_session
        out = await plan(
            action="update_step",
            plan_id="p1",
            step_id="s1",
            status="completed",
            result="",
            config=_config(),
        )
        assert out.startswith("Error:")
        assert "result" in out
        assert step.status == "pending"

    async def test_completed_with_whitespace_result_rejected(self, _fake_session):
        step, _ = _fake_session
        out = await plan(
            action="update_step",
            plan_id="p1",
            step_id="s1",
            status="completed",
            result="   ",
            config=_config(),
        )
        assert out.startswith("Error:")
        assert step.status == "pending"

    async def test_completed_with_result_accepted(self, _fake_session):
        step, _ = _fake_session
        out = await plan(
            action="update_step",
            plan_id="p1",
            step_id="s1",
            status="completed",
            result="查完库存，缺货商品已下架",
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert step.status == "completed"
        assert step.result == "查完库存，缺货商品已下架"

    async def test_long_result_truncated(self, _fake_session):
        step, _ = _fake_session
        out = await plan(
            action="update_step",
            plan_id="p1",
            step_id="s1",
            status="completed",
            result="x" * 800,
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert len(step.result) == 500

    async def test_in_progress_without_result_still_allowed(self, _fake_session):
        step, _ = _fake_session
        out = await plan(
            action="update_step",
            plan_id="p1",
            step_id="s1",
            status="in_progress",
            result="",
            config=_config(),
        )
        assert not out.startswith("Error:")
        assert step.status == "in_progress"
