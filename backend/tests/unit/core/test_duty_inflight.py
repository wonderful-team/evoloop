"""防积压：调度投递层「在飞登记」机制。

背景：SchedulerService.dispatch_task 只认 next_run_at<=now 就 .delay() 投递，
不感知该 (project_id, kind) 是否已在飞（排队中或执行中）。单轮执行时长 >
interval 时，每 60s tick 都会再投一份，Huey 队列（持久化）持续积压重复副本。

修复：投递前 try_claim_inflight 登记；run_duty_poll 执行结束 finally 释放；
带超时兜底（防 worker 异常导致永久卡死）。
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel.duty import scheduler as duty_scheduler


@pytest.fixture(autouse=True)
def _reset_inflight():
    """每个测试后清空在飞登记，避免跨用例污染。"""
    yield
    duty_scheduler._inflight.clear()


# ── 核心原语：try_claim / release ─────────────────────────

def test_claim_then_release_allows_reclaim():
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True
    # 未释放前再次 claim → 失败（已在飞）
    assert duty_scheduler.try_claim_inflight(7, "wecom") is False
    duty_scheduler.release_inflight(7, "wecom")
    # 释放后可再次 claim
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True


def test_different_kind_independent():
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True
    # 同项目不同 kind：互不影响
    assert duty_scheduler.try_claim_inflight(7, "business_poll") is True
    assert duty_scheduler.try_claim_inflight(7, "wecom") is False


def test_different_project_independent():
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True
    # 不同项目同 kind：互不影响
    assert duty_scheduler.try_claim_inflight(8, "wecom") is True
    assert duty_scheduler.try_claim_inflight(7, "wecom") is False


def test_timeout_releases_stale_claim():
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True
    # 超时后，陈旧登记被判定为可重新 claim（兜底防卡死）
    duty_scheduler._inflight[(7, "wecom")] = time.monotonic() - duty_scheduler._INFLIGHT_TIMEOUT - 1
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True
    # 且陈旧登记被覆盖更新
    assert duty_scheduler._inflight[(7, "wecom")] > time.monotonic() - 1


# ── 调度层集成：dispatch_task 在飞时跳过投递 ───────────────

class _FakeTask:
    """最小 AutonomousTask 假对象。"""

    def __init__(self, task_id, project_id, kind, is_active=True):
        self.id = task_id
        self.project_id = project_id
        self.params_template = {"duty_channel": "wecom_duty", "kind": kind}
        self.trigger_spec = "interval:60"
        self.last_run_at = None
        self.next_run_at = None
        self.is_active = is_active


async def _dispatch_duty(task, run_mock):
    """调用 dispatch_task 的 duty 分支（patch 掉 DB 与轮巡执行）。"""
    from app.infrastructure.scheduler import service as svc

    session = MagicMock()
    session.get = AsyncMock(return_value=task)
    scope_cm = MagicMock()
    scope_cm.__aenter__ = AsyncMock(return_value=session)
    scope_cm.__aexit__ = AsyncMock(return_value=False)

    # dispatch_task 函数体内 `from app.core.channel.duty.scheduler import
    # run_duty_poll_with_release`，故 patch 源模块以拦截轮巡执行。
    with patch.object(svc, "session_scope", return_value=scope_cm), patch.object(
        duty_scheduler, "run_duty_poll_with_release", new=run_mock
    ):
        await svc.SchedulerService.dispatch_task(task.id)


async def test_dispatch_skips_second_while_inflight():
    """同一 (project, kind) 在飞未释放时，第二次 dispatch 不执行轮巡。"""
    task = _FakeTask(1, 7, "wecom")
    run_mock = AsyncMock()

    await _dispatch_duty(task, run_mock)
    # 第一次执行轮巡
    assert run_mock.await_count == 1

    # 未释放（模拟上一轮还在飞）→ 第二次 dispatch 跳过执行
    await _dispatch_duty(task, run_mock)
    assert run_mock.await_count == 1

    # 释放后，第三次 dispatch 恢复执行
    duty_scheduler.release_inflight(7, "wecom")
    await _dispatch_duty(task, run_mock)
    assert run_mock.await_count == 2


async def test_dispatch_unknown_kind_retires_task():
    """已下线的值守 kind（不在 KIND_CHANNEL_MAP）→ 任务停用且不执行轮巡。"""
    task_biz = _FakeTask(2, 7, "business_poll")
    run_mock = AsyncMock()

    await _dispatch_duty(task_biz, run_mock)
    assert run_mock.await_count == 0
    assert task_biz.is_active is False


# ── run_duty_poll 执行结束释放登记 ─────────────────────────

async def test_run_duty_poll_releases_inflight_on_success():
    """run_duty_poll 正常执行结束后，在飞登记被释放。"""
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True

    with patch.object(
        duty_scheduler, "_run_duty_poll_impl", AsyncMock(return_value=3)
    ):
        result = await duty_scheduler.run_duty_poll_with_release(
            project_id=7, kind="wecom"
        )

    assert result == 3
    # 执行结束后登记被释放 → 可再次 claim
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True


async def test_run_duty_poll_releases_inflight_on_error():
    """run_duty_poll 执行抛异常时，登记仍被释放（finally 兜底）。"""
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True

    with patch.object(
        duty_scheduler, "_run_duty_poll_impl",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(RuntimeError):
            await duty_scheduler.run_duty_poll_with_release(
                project_id=7, kind="wecom"
            )

    # 异常后登记被释放
    assert duty_scheduler.try_claim_inflight(7, "wecom") is True
