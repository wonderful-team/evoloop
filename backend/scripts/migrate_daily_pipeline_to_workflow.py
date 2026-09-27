"""One-shot migration: "recurring 根 + 一次性依赖子树" 提案 → 周期工作流。

背景（2026-09-25 #T-1 事故，docs/autonomous-task-loop.md 断层记录）：
Agent 用 recurring 根任务 + one-shot 子任务 + 依赖边表达"每日流水线"，
但队列没有编排原语——根任务每天只驱动自己，子任务一次性跑完躺尸，
且依赖接线与 Agent 自述的 DAG 不符（#5/6/7 全挂在 #T-2 上）。

本脚本把指定 origin 会话派生的提案树转换为 WorkflowService 周期工作流：
- 根任务的 title/goal/trigger_spec → 工作流模板（status=proposed 待确认）；
- 子任务 → 阶段模板（deps 按 Agent 自述 DAG 修正：汇总←三路采集、
  草稿/校准←汇总）；
- 原 7 条提案行全部 cancelled（reason=workflow_migrated），画布隐藏。
幂等：同一 origin thread 重复执行零转换。

Usage (from backend/):
    uv run python scripts/migrate_daily_pipeline_to_workflow.py \
        --origin-thread c72b12d5-36bd-4ebe-8cfd-c8c20df956e7 --dry-run
    uv run python scripts/migrate_daily_pipeline_to_workflow.py ... --execute
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# 子任务标题 → 阶段 key（子串匹配；deps 按 Agent 自述 DAG 修正：
# 汇总←三路采集，草稿/校准←汇总，草稿与校准可并行）
STAGE_KEY_BY_PREFIX = {
    "采集 HN": ("collect_hn", []),
    "采集 Reddit": ("collect_reddit", []),
    "采集 V2EX": ("collect_v2ex", []),
    "线索汇总": ("aggregate", ["collect_hn", "collect_reddit", "collect_v2ex"]),
    "外联草稿": ("draft_outreach", ["aggregate"]),
    "校准评分": ("calibrate_rules", ["aggregate"]),
}


def _stage_key_for(title: str) -> tuple[str, list[str]] | None:
    for prefix, value in STAGE_KEY_BY_PREFIX.items():
        if prefix in title:
            return value
    return None


async def migrate(origin_thread_id: str, *, execute: bool) -> None:
    from sqlalchemy import select, update

    from app.domain.tasks.events import publish_task_queue_event
    from app.domain.tasks.schemas import WorkflowStageSpec
    from app.domain.tasks.service import TaskQueueService, task_title
    from app.domain.tasks.workflows import WorkflowService
    from app.infrastructure.database import resource_manager
    from app.infrastructure.database.sql.database import session_scope
    from app.models.project import ProjectTask
    from app.models.task_workflow import TaskWorkflow

    await resource_manager.db_resource_manager.initialize(create_tables=False)

    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(ProjectTask)
                    .where(
                        ProjectTask.origin_thread_id == origin_thread_id,
                        ProjectTask.status.notin_(("cancelled",)),
                    )
                    .order_by(ProjectTask.task_no.asc())
                )
            )
            .scalars()
            .all()
        )
    roots = [t for t in rows if t.parent_id is None]
    children = [t for t in rows if t.parent_id is not None]
    if not roots or not children:
        print(f"nothing to migrate: roots={len(roots)} children={len(children)}")
        return

    # 幂等：同一 origin thread 已迁移过 → 零转换（inputs JSON 跨方言差异，
    # 直接取全量在 Python 侧匹配，量级=工作流总数，可忽略）
    async with session_scope() as session:
        workflows = (await session.execute(select(TaskWorkflow))).scalars().all()
    existing = next(
        (
            w
            for w in workflows
            if (w.inputs or {}).get("origin_thread_id") == origin_thread_id
        ),
        None,
    )
    if existing is not None:
        print(f"already migrated: workflow {existing.id} (status={existing.status})")
        return

    root = roots[0]
    stages: list[WorkflowStageSpec] = []
    for child in sorted(children, key=lambda t: int(t.task_no or 0)):
        title = task_title(child) or ""
        mapped = _stage_key_for(title)
        if mapped is None:
            print(f"  abort: unmappable child #{child.task_no}「{title}」")
            return
        key, deps = mapped
        stages.append(
            WorkflowStageSpec(
                key=key,
                title=title,
                description=child.description or "",
                category=child.category,
                priority=child.priority or "medium",
                risk_level=child.risk_level,
                deps=deps,
            )
        )

    print(
        f"plan: workflow「{task_title(root) or root.id}」trigger={root.trigger_spec} "
        f"stages={[s.key for s in stages]}"
    )
    if not execute:
        print("[dry-run] no changes written")
        return

    workflow = await WorkflowService.create_workflow(
        project_id=root.project_id or 0,
        member_id=root.member_id or 0,
        title=task_title(root) or root.id,
        goal=root.description or "",
        trigger_spec=root.trigger_spec,
        origin_thread_id=origin_thread_id,
        stages=stages,
    )
    print(
        f"workflow created: {workflow.id} (status=proposed, 待 /workflows/{workflow.id}/confirm)"
    )

    for t in rows:
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == t.id,
                    ProjectTask.status.notin_(("completed", "failed", "cancelled")),
                )
                .values(
                    status="cancelled",
                    last_result="workflow_migrated:" + workflow.id,
                    version=ProjectTask.version + 1,
                )
            )
        fresh = await TaskQueueService.get_task(t.id)
        if fresh is not None:
            await publish_task_queue_event(
                fresh, event="task_advanced", extra={"reason": "workflow_migrated"}
            )
    print(f"cancelled {len(rows)} proposal row(s); idempotent re-run is safe")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin-thread", required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    asyncio.run(migrate(args.origin_thread, execute=args.execute))


if __name__ == "__main__":
    main()
