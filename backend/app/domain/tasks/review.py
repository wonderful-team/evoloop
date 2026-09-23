"""Task reviewer loop (原对话评审).

Design (user-approved 2026-09-19):
- A task completed by the duty agent is NOT accepted by "system:auto" when it
  has an origin conversation (task.origin_thread_id). Instead the result is
  pushed back to the origin dialogue as a system-on-behalf-of-user message and
  the origin agent — the one who derived the task from the user's own words —
  reviews it from the user's standpoint (对抗执行者的自我辩护偏差).
- The reviewer is NOT given the executor's report dump as "the goal": only the
  executor's final reply is quoted as the object of review, while the source
  of truth for intent remains the origin conversation history which the
  reviewer walks itself.
- Reviewer is read-only (audit only, never implements).
- Rejection loop is bounded: at most 2 reviewer rejections → task failed +
  arbitration message back to the origin dialogue (no infinite rework).

Red lines honored:
- The executor cannot self-accept (tasks facade has no submit_acceptance).
- Only the reviewer (a different run context from the executor) may drive the
  state machine, with receipt by="reviewer:auto" for auditability.
"""

import asyncio
import logging

from app.core.engine.agent import run_agent_background
from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
from app.domain.tasks.service import (
    TaskQueueService,
    task_number,
    task_review_pending,
    task_title,
)

logger = logging.getLogger(__name__)


async def _latest_executor_reply(thread_id: str) -> str:
    """The run's final assistant reply on this thread (prose text only).

    The messages table stores tool-call carrier rows (empty content) and
    tool outputs under role=ai/assistant too — filter to the assistant
    response category so the reviewer verdict is not read from an empty
    carrier row.
    """
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.conversation import Message

    async with session_scope() as session:
        stmt = (
            select(Message.content)
            .where(
                Message.thread_id == thread_id,
                Message.role == "ai",
                Message.category.in_(("assistant_response", "assistant_text")),
                Message.content.isnot(None),
                Message.content != "",
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar()
        return str(row or "")


async def _dispatch_to_thread(
    thread_id: str,
    content: str,
    project_id: int,
    member_id: int,
    source_task_id: str,
) -> bool:
    """Send a system-on-behalf-of-user message into the origin dialogue and
    start a reviewer run there. Reuses the duty dispatch path (same message
    persistence + agent run machinery)."""
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=content,
        project_id=project_id,
        member_id=member_id,
        metadata={
            "source": "task_review",
            "source_task_id": source_task_id,
            "channel_name": "",
        },
    )
    if result.status == DispatchStatus.FAILED:
        logger.error("[TaskReview] dispatch failed for task %s: %s", source_task_id, result.error)
        return False
    if result.inputs:
        asyncio.create_task(run_agent_background(thread_id, result.inputs))
    return True


async def trigger_review(task) -> None:
    """Entry: push the finished task's result back to its origin dialogue."""
    origin = getattr(task, "origin_thread_id", None)
    if not origin:
        return
    task_no = task_number(task)
    label = f"#T-{task_no}" if task_no else task.id[:8]
    title = task_title(task) or ""
    reply = await _latest_executor_reply(task.last_thread_id or "")
    content = (
        f"[值守系统代用户] 任务 {label}「{title}」已由值守执行完成。\n\n"
        f"执行者任务级会话的最终回复如下（这只是执行者的汇报，不代表我的意图）：\n"
        f"---\n{reply[:4000]}\n---\n\n"
        f"请你以我的立场评审核实该任务的完成情况（只评审，不实施；不要修改任何数据、"
        f"不要执行任何写操作，只允许查询类工具用于抽查验证）：\n"
        f"1) 回顾本对话中我最初提出这件事的意图与预期，以我的原始表述为准，"
        f"不要以执行报告的自我描述为准；\n"
        f"2) 对照执行者的最终回复，逐条核对目标是否达成；关键数字与清单要交叉验证；\n"
        f"3) 有无遗漏、漂移或只完成了一部分的迹象。\n\n"
        f"最后一行必须是结论，格式严格如下：\n"
        f"结论：通过\n"
        f"或\n"
        f"结论：不通过：<具体证据与差距，指出必须修复项（限定范围，不扩大）>"
    )
    member_id = await TaskQueueService.resolve_member_id(task)
    ok = await _dispatch_to_thread(
        thread_id=origin,
        content=content,
        project_id=task.project_id,
        member_id=member_id,
        source_task_id=task.id,
    )
    if not ok:
        # 回灌失败（对话不存在/派发失败）：保持 waiting_acceptance——评审
        # 闸门绝不放水（执行者结果不得因基础设施故障自我验收）。挂死由
        # reconciler 的 30min 评审超时兜底收敛（空结论=不通过 → 2 轮上限）。
        logger.error(
            "[TaskReview] dispatch failed for %s; keeping waiting_acceptance "
            "(30min review-timeout backstop will converge)",
            task.id,
        )


async def notify_arbitration(task, feedback: str) -> None:
    """Two review rounds failed: escalate to the origin dialogue (final state)."""
    origin = getattr(task, "origin_thread_id", None)
    if not origin:
        return
    task_no = task_number(task)
    label = f"#T-{task_no}" if task_no else task.id[:8]
    title = task_title(task) or ""
    content = (
        f"[值守系统代用户] 任务 {label}「{title}」经两轮评审仍未通过，"
        f"已停止自动返工，转人工仲裁。\n"
        f"最后一轮评审意见：{feedback[:600]}\n"
        f"请在对话里决定下一步（重新下任务 / 调整目标后重开 / 放弃）。"
    )
    await _dispatch_to_thread(
        thread_id=origin,
        content=content,
        project_id=task.project_id,
        member_id=await TaskQueueService.resolve_member_id(task),
        source_task_id=task.id,
    )


async def resolve_review_verdict(task_id: str, reviewer_reply: str) -> None:
    """Parse the reviewer's final reply and drive the acceptance state machine.

    Called from the RunCompleted subscriber for origin threads with a task in
    review-pending state. Unparseable verdict → treated as rejection (bounded
    by the 2-round cap; the task re-runs once, then escalates to human).
    """
    text = (reviewer_reply or "").strip()
    # 全角/半角冒号统一（"结论：通过" / "结论:通过" 都接受）
    normalized = text.replace("：", ":").replace(" ", "").replace("\u3000", "")
    tail = normalized[-400:]
    if "结论:通过" in tail or "结论:pass" in tail.lower():
        verdict, feedback = "accepted", ""
    else:
        import re as _re

        m = _re.search(r"结论[:：]\s*不通过[:：]?\s*(.+)", text[-1000:], _re.S)
        if m:
            verdict = "rejected"
            feedback = m.group(1).strip()[:800]
        else:
            verdict = "rejected"
            feedback = (
                "评审回复中没有给出明确的『结论：通过/不通过』结论行，视为未通过；"
                "执行者请补充完成并在下次汇报时给出一句话结论。"
            )
            logger.warning(
                "[TaskReview] no explicit verdict line for task %s; treating as rejection",
                task_id,
            )

    task = await TaskQueueService.get_task(task_id)
    if task is None or task.status != "waiting_acceptance":
        return
    if not task_review_pending(task):
        return  # human acceptance path, reviewer arrives late — ignore

    await TaskQueueService.submit_acceptance(
        task_id, by="reviewer:auto", verdict=verdict, feedback=feedback
    )
