"""Unit tests for task-level skill attachment and prompt injection."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.domain.tasks.runtime.dispatcher import _run_wakeup_with_deadline, dispatch_due_tasks
from app.domain.tasks.service import TaskQueueService, task_skills
from app.domain.tasks.workflows import WorkflowService


@pytest.mark.asyncio
async def test_create_and_edit_task_with_skills():
    """Verify task skills persist in task_data and are queryable."""
    task = await TaskQueueService.create_task(
        project_id=1,
        title="Test Scrape Task",
        skills=["agent-reach"],
    )
    assert task_skills(task) == ["agent-reach"]

    # Edit skills
    updated = await TaskQueueService.edit_task(
        task.id,
        skills=["agent-reach", "browser-operator"],
    )
    assert task_skills(updated) == ["agent-reach", "browser-operator"]


@pytest.mark.asyncio
async def test_spawn_round_propagates_stage_skills():
    """Verify workflow round spawn propagates stage skills to stage tasks."""
    from app.domain.tasks.schemas import WorkflowStageSpec

    stages = [
        WorkflowStageSpec(
            key="crawl",
            title="Crawl Leads",
            skills=["agent-reach"],
            deps=[],
        ),
        WorkflowStageSpec(
            key="process",
            title="Process Leads",
            deps=["crawl"],
        ),
    ]
    wf = await WorkflowService.create_workflow(
        project_id=1,
        title="Lead Pipeline",
        goal="Collect leads",
        stages=stages,
    )
    armed = await WorkflowService.confirm_workflow(wf.id)
    assert armed.status == "armed"

    tasks = await WorkflowService.spawn_round(wf.id)
    crawl_task = next(t for t in tasks if t.title == "Crawl Leads")
    process_task = next(t for t in tasks if t.title == "Process Leads")

    assert task_skills(crawl_task) == ["agent-reach"]
    assert task_skills(process_task) == []


@pytest.mark.asyncio
async def test_dispatcher_prepends_skill_directive_and_metadata():
    """Verify dispatcher prepends directive and injects skills into metadata."""
    task = await TaskQueueService.create_task(
        project_id=0,
        title="Collect Reddit Info",
        description="Search Reddit for discussions.",
        skills=["agent-reach"],
        source="user",
    )

    dispatched_args = {}

    async def mock_dispatch_agent_run(**kwargs):
        from app.core.engine.dispatch import DispatchStatus

        dispatched_args.update(kwargs)
        return SimpleNamespace(
            status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
        )

    with patch(
        "app.core.engine.dispatch.dispatch_agent_run",
        side_effect=mock_dispatch_agent_run,
    ), patch(
        "app.domain.tasks.runtime.dispatcher._run_wakeup_with_deadline",
        new=AsyncMock(),
    ):
        await dispatch_due_tasks()

    assert "message_content" in dispatched_args
    content = dispatched_args["message_content"]
    assert "【专用技能指引】" in content
    assert "agent-reach" in content
    assert "严禁自行编写并调试原生爬虫" in content

    meta = dispatched_args["metadata"]
    assert meta["duty_task"]["skills"] == ["agent-reach"]


@pytest.mark.asyncio
async def test_prompts_renders_required_skills_block():
    """Verify prompts.py renders required_skills_block in main.duty.task.txt."""
    from app.core.context.manager import ContextManager, EvoContext
    from app.core.engine.react.prompts import build_system_prompt

    ctx = EvoContext(
        thread_id="test_th",
        project_id=1,
        metadata={
            "source": "duty",
            "duty_task": {
                "id": "t-123",
                "title": "Crawl Data",
                "status": "in_progress",
                "priority": "medium",
                "risk": "T3",
                "due": "now",
                "category": "default",
                "skills": ["agent-reach"],
            },
        },
    )
    ContextManager.set(ctx)

    config = {
        "metadata": {
            "source": "duty",
            "duty_task": ctx.metadata["duty_task"],
        }
    }
    prompt = await build_system_prompt(state=None, config=config)
    assert "专用技能" in prompt
    assert "`agent-reach`" in prompt
    assert "切勿自行编写并调试原生爬虫" in prompt

