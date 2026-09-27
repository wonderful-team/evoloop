"""值守唤醒域解析契约测试（2026-09-18：任务值守接入 L1 域标注）。

优先级：项目 profile 唯一声明域（≈host 权威）> L1 域标注兜底 > None
（fail-open：全量面 + 包反哺兜底）。L1 与文本消息 skip_l0 路径同源组件、
同置信度门槛（CONFIDENCE_THRESHOLD）。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.tasks.runtime.dispatcher import resolve_wakeup_domain


@pytest.fixture
def _routing(monkeypatch):
    """打补丁：项目路径/域声明/L1 推理。返回 setter 便于逐用例定制。"""
    state = {"project_dir": "/proj", "domains": [], "label": None, "conf": 0.0}

    async def fake_get_project_path(_project_id):
        return state["project_dir"]

    def fake_predict(_text):
        return state["label"], state["conf"]

    monkeypatch.setattr(
        "app.core.project.utils.get_project_path", fake_get_project_path
    )
    monkeypatch.setattr(
        "app.core.engine.capability_profiles.list_domains",
        lambda wd: state["domains"],
    )
    monkeypatch.setattr(
        "app.core.routing.domain_classifier.predict", fake_predict
    )
    return state


@pytest.mark.asyncio
async def test_workspace_project_fails_open(_routing):
    """pid=0 工作空间任务不绑项目域 → 直接 fail-open，不跑 L1。

    2026-09-23 实测事故回归：Upwork 侦察轮描述被 L1 高置信分类为
    ecommerce，误继承商城 profile 的 native_tools 白名单（无 bash/文件
    工具）→ opencli/落盘全断。工作空间任务按设计就是全量面。
    """
    _routing.update(label="ecommerce", conf=0.95)

    with patch(
        "app.core.routing.domain_classifier.predict", side_effect=AssertionError
    ) as spy:
        domain, reason = await resolve_wakeup_domain(0, "拉取 Upwork 挂单流")

    assert domain is None and reason == ""
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_profile_unique_domain_wins_without_l1(_routing):
    """项目声明唯一域 → 直接采用，不跑 L1（profile-first ≈ host 权威）。"""
    _routing.update(domains=["mall_ops"])

    with patch(
        "app.core.routing.domain_classifier.predict", side_effect=AssertionError
    ) as spy:
        domain, reason = await resolve_wakeup_domain(183, "查待发货订单")

    assert domain == "mall_ops"
    assert reason == "duty wakeup (project profile)"
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_l1_fallback_when_no_profile_domain(_routing):
    """项目未声明域 → L1 兜底；高置信标签成为域信号（alias 可接）。"""
    _routing.update(label="ecommerce", conf=0.92)

    domain, reason = await resolve_wakeup_domain(
        183, "调用商城工具查询当前待发货订单"
    )
    assert domain == "ecommerce"
    assert reason == "duty wakeup (L1)"


@pytest.mark.asyncio
async def test_low_confidence_fails_open(_routing):
    """低置信 → None（fail-open：全量面 + 包反哺兜底，无回归）。"""
    _routing.update(label="ecommerce", conf=0.3)

    domain, reason = await resolve_wakeup_domain(183, "随便查查")
    assert domain is None and reason == ""


@pytest.mark.asyncio
async def test_multi_domain_profile_falls_through_to_l1(_routing):
    """项目声明多个域（歧义）→ 不采用，落 L1 兜底。"""
    _routing.update(domains=["mall_ops", "other"], label="ecommerce", conf=0.9)

    domain, _ = await resolve_wakeup_domain(183, "查订单")
    assert domain == "ecommerce"


@pytest.mark.asyncio
async def test_empty_instruction_skips_l1(_routing):
    """空指令 → None（不浪费一次推理）。"""
    with patch(
        "app.core.routing.domain_classifier.predict", side_effect=AssertionError
    ):
        domain, _ = await resolve_wakeup_domain(183, "  ")
    assert domain is None
