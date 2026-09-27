"""One-shot migration: business_poll_prompts (project.json) -> recurring Tasks.

Stage 3 of the autonomous task loop (docs/autonomous-task-loop.md §6.1/§11).

Design notes:
- description carries the FULL executable instruction (single source; the
  agent reads this). No parallel checklist field — it duplicated the prompt.
- category/priority are informational today (engine consumes only
  risk_level/due_at/trigger_spec/next_run_at/status).
- legacy KIND_BUSINESS_POLL AutonomousTask rows get deactivated.
- idempotent: dedup_key = "business_poll_migrated:{original_id}"

Usage (from backend/):
    uv run python scripts/migrate_business_poll.py --project-json <path> \
        --project-id 120 --dry-run
    uv run python scripts/migrate_business_poll.py ... --execute --enable-migrated
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))



def _tpl(title: str, category: str, prompt: str) -> dict:
    # The prompt IS the full instruction (single source of truth for the agent).
    # category is informational (board filter, stage 4) — the engine does not
    # consume it. No parallel checklist: it only duplicated the prompt.
    return {"title": title, "category": category, "prompt": prompt}


CHECKLISTS: dict[str, dict] = {
    "poll-orders-pending": _tpl(
        "订单巡检",
        "orders",
        "订单巡检：用 mall MCP 工具检查是否有待发货、待付款或异常订单。"
        "异常按风险档处理：可直接修复的（T3/T4）当场处理并在结果留痕；"
        "资金类（T1/T2）建提案任务，不自行执行。"
        "全部无异常时在结果中报告『本次订单巡检无待办』。",
    ),
    "poll-refunds-pending": _tpl(
        "售后巡检",
        "refunds",
        "售后巡检：用 mall MCP 工具检查待处理的退款、退货、换货工单。"
        "退款/转账属 T1/T2 资金操作：只建提案或挂起等人工，禁止自行执行。"
        "全部无异常时在结果中报告『本次售后巡检无待办』。",
    ),
    "poll-low-stock": _tpl(
        "库存巡检",
        "stock",
        "库存巡检：用 mall MCP 工具检查低库存预警（stock_alarm 阈值）、"
        "缺货仍在架商品、库存异动异常。可下架缺货商品（T3）并留痕；"
        "需补货的建提案任务（附商品与销量证据），不自行采购。"
        "全部无异常时在结果中报告『本次库存巡检无待办』。",
    ),
    "poll-member-abnormal": _tpl(
        "会员巡检",
        "member",
        "会员巡检：用 mall MCP 工具检查会员投诉、等级/积分异常。"
        "会员提现审批属 T1 资金操作：仅汇报数量或建提案任务，禁止任何执行动作。"
        "全部无异常时在结果中报告『本次会员巡检无待办』。",
    ),
    "poll-promotion-expiring": _tpl(
        "营销巡检",
        "promotion",
        "营销巡检：用 mall MCP 工具检查即将到期、异常或待生效的促销活动/优惠券。"
        "到期续期类（T3）可直接处理并留痕；影响面大的先建提案说明方案。"
        "全部无异常时在结果中报告『本次营销巡检无待办』。",
    ),
    "poll-finance-abnormal": _tpl(
        "资金巡检",
        "finance",
        "资金巡检：用 mall MCP 工具检查结算异常、提现审批、对账差异或资金风险。"
        "全部属 T1/T2：发现即建提案任务（附金额/单号证据），禁止任何执行动作。"
        "全部无异常时在结果中报告『本次资金巡检无待办』。",
    ),
}


async def migrate(
    project_json: Path,
    project_id: int,
    execute: bool,
    enable_migrated: bool = False,
) -> int:
    raw = json.loads(project_json.read_text(encoding="utf-8"))
    prompts = (raw.get("customer_service_duty") or {}).get(
        "business_poll_prompts"
    ) or []
    if not prompts:
        print("no business_poll_prompts found; nothing to migrate")
        return 0

    from app.domain.tasks.service import TaskQueueError, TaskQueueService
    from app.infrastructure.database import resource_manager

    await resource_manager.db_resource_manager.initialize(create_tables=False)

    created, skipped = 0, 0
    for p in prompts:
        pid = str(p.get("id") or "")
        if not pid:
            continue
        meta = CHECKLISTS.get(pid)
        if meta is None:
            print(f"  skip (no template): {pid}")
            continue
        enabled = p.get("enabled", True) or enable_migrated
        if not enabled and not execute:
            print(f"  skip (disabled): {pid}")
            continue
        interval_minutes = int(p.get("interval_minutes") or 60)
        if not execute:
            print(
                f"  [dry-run] {meta['title']} | interval:{interval_minutes * 60} "
                f"| category={meta['category']} | prompt={len(meta['prompt'])} chars"
            )
            created += 1
            continue
        try:
            task = await TaskQueueService.create_task(
                project_id=project_id,
                title=meta["title"],
                description=meta["prompt"],
                source="user",
                source_ref={
                    "kind": "migrated",
                    "from": "business_poll_prompts",
                    "original_id": pid,
                },
                category=meta["category"],
                priority="medium",
                risk_level="T3",
                trigger_spec=f"interval:{interval_minutes * 60}",
                dedup_key=f"business_poll_migrated:{pid}",
            )
            created += 1
            print(f"  ok (idempotent): {task.id} <- {pid}")
        except TaskQueueError as e:
            skipped += 1
            print(f"  skip (dedup): {pid} -> {e}")

    if execute:
        from sqlalchemy import select, update

        from app.infrastructure.database.sql.database import session_scope
        from app.models.scheduler import AutonomousTask

        async with session_scope() as session:
            rows = (
                (await session.execute(select(AutonomousTask))).scalars().all()
            )
            legacy = [
                t
                for t in rows
                if (t.params_template or {}).get("kind") == "business_poll"
            ]
            for t in legacy:
                if t.is_active:
                    await session.execute(
                        update(AutonomousTask)
                        .where(AutonomousTask.id == t.id)
                        .values(is_active=False)
                    )
                    print(f"  deactivated legacy trigger: task {t.id}")
    return created


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-json", required=True)
    ap.add_argument("--project-id", type=int, required=True)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--execute", action="store_true")
    ap.add_argument(
        "--enable-migrated",
        action="store_true",
        help="enable migrated patrols even if the legacy prompt was disabled",
    )
    args = ap.parse_args()

    created = asyncio.run(
        migrate(
            Path(args.project_json),
            args.project_id,
            args.execute,
            args.enable_migrated,
        )
    )
    print(f"done: {created} task(s) {'planned' if args.dry_run else 'created'}")


if __name__ == "__main__":
    main()
