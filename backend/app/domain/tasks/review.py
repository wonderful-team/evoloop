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
    task_last_result,
    task_number,
    task_review_pending,
    task_title,
)

logger = logging.getLogger(__name__)


async def _latest_ai_reply(thread_id: str, *, assistant_categories_only: bool) -> str:
    """该线程最后一条非空 ai 回复（单一查询实现，2026-09-25 合并）。

    messages 表在 role=ai 下还存 tool-call 载体行（空 content）与工具
    输出——``assistant_categories_only=True`` 时过滤到 assistant 响应类目，
    评审结论不会从空载体行读出（执行者汇报读取用）；False 时取任意类目
    的最后一条非空 ai 消息（评审者结论回退读取用）。

    排序必须用 ``sequence_number``（线程内单调序）：``id`` 是随机 UUID，
    按 id 降序取到的是"随机一条"而非"最新一条"——评审结论行会时有时无，
    曾致无结论=不通过的间歇性误判（2026-09-27 实测：同一回复有时读得到
    有时读不到）。
    """
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.conversation import Message

    conditions = [
        Message.thread_id == thread_id,
        Message.role == "ai",
        Message.content.isnot(None),
        Message.content != "",
    ]
    if assistant_categories_only:
        conditions.append(
            Message.category.in_(("assistant_response", "assistant_text"))
        )
    async with session_scope() as session:
        stmt = (
            select(Message.content)
            .where(*conditions)
            .order_by(Message.sequence_number.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar()
        return str(row or "")


async def _latest_executor_reply(thread_id: str) -> str:
    """执行者最终汇报（assistant 响应类目过滤，见 _latest_ai_reply）。"""
    return await _latest_ai_reply(thread_id, assistant_categories_only=True)


async def _dispatch_to_thread(
    thread_id: str,
    content: str,
    project_id: int,
    member_id: int,
    source_task_id: str,
    references: list[dict] | None = None,
) -> bool:
    """Send a system-on-behalf-of-user message into the origin dialogue and
    start a reviewer run there. Reuses the duty dispatch path (same message
    persistence + agent run machinery)."""
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=content,
        references=references,
        project_id=project_id,
        member_id=member_id,
        metadata={
            "source": "task_review",
            "source_task_id": source_task_id,
            "channel_name": "",
        },
    )
    if result.status == DispatchStatus.FAILED:
        logger.error(
            "[TaskReview] dispatch failed for task %s: %s", source_task_id, result.error
        )
        return False
    if result.inputs:
        asyncio.create_task(run_agent_background(thread_id, result.inputs))
    return True


async def _get_review_references(task) -> tuple[list[dict], str]:
    """Gather structured references (execution thread + deliverables/artifacts)
    and executor result summary for review decoupling.
    """
    from sqlalchemy import select

    from app.infrastructure.database.sql.database import session_scope
    from app.models.conversation import Message, MessageReference
    from app.models.task_workflow import TaskArtifact

    refs: list[dict] = []
    seen_targets: set[str] = set()
    latest_reply = ""

    task_no = task_number(task)
    label = f"#T-{task_no}" if task_no else task.id[:8]

    try:
        async with session_scope() as session:
            # 1. Execution session reference: point to the executor thread's latest AI message
            if task.last_thread_id:
                msg_stmt = (
                    select(Message.id, Message.content)
                    .where(
                        Message.thread_id == task.last_thread_id,
                        Message.role == "ai",
                        Message.category.in_(("assistant_response", "assistant_text")),
                        Message.content.isnot(None),
                        Message.content != "",
                    )
                    .order_by(Message.sequence_number.desc())
                    .limit(1)
                )
                msg_row = (await session.execute(msg_stmt)).first()
                if msg_row:
                    msg_id, content = msg_row
                    latest_reply = str(content or "")
                    refs.append(
                        {
                            "type": "message",
                            "target_id": str(msg_id),
                            "target_name": f"执行会话 ({label})",
                            "name": f"执行会话 ({label})",
                            "metadata": {
                                "thread_id": task.last_thread_id,
                                "task_id": task.id,
                                "snippet": latest_reply[:200],
                            },
                        }
                    )
                    seen_targets.add(str(msg_id))

            # 2. Structured TaskArtifact rows
            ta_stmt = select(TaskArtifact).where(TaskArtifact.task_id == task.id)
            for ta in (await session.execute(ta_stmt)).scalars():
                target = (
                    (ta.data or {}).get("file_path")
                    or (ta.data or {}).get("path")
                    or (ta.data or {}).get("url")
                    or ta.summary
                )
                name = (ta.data or {}).get("name") or ta.artifact_type or "交付产物"
                if target and str(target) not in seen_targets:
                    seen_targets.add(str(target))
                    refs.append(
                        {
                            "type": "file",
                            "target_id": str(target),
                            "target_name": str(name),
                            "name": str(name),
                            "metadata": {"source_path": str(target), "artifact_id": ta.id},
                        }
                    )

            # 3. File / image / artifact references produced during the executor run
            if task.last_thread_id:
                mr_stmt = (
                    select(MessageReference)
                    .join(Message, MessageReference.message_id == Message.id)
                    .where(
                        Message.thread_id == task.last_thread_id,
                        MessageReference.type.in_(("file", "image", "artifact", "directory")),
                    )
                )
                for mr in (await session.execute(mr_stmt)).scalars():
                    if mr.target_id and mr.target_id not in seen_targets:
                        seen_targets.add(mr.target_id)
                        refs.append(
                            {
                                "type": mr.type,
                                "target_id": mr.target_id,
                                "target_name": mr.target_name or "交付物",
                                "name": mr.target_name or "交付物",
                                "metadata": mr.meta_data or {},
                            }
                        )
    except Exception as e:
        logger.warning("[TaskReview] failed to collect references: %s", e)

    return refs, latest_reply


async def trigger_review(task) -> None:
    """Entry: push the finished task's result back to its origin dialogue."""
    origin = getattr(task, "origin_thread_id", None)
    if not origin:
        return
    task_no = task_number(task)
    label = f"#T-{task_no}" if task_no else task.id[:8]
    title = task_title(task) or ""

    refs, latest_reply = await _get_review_references(task)

    result_summary = task_last_result(task) or ""
    if not result_summary:
        if not latest_reply:
            latest_reply = await _latest_executor_reply(task.last_thread_id or "")
        result_summary = latest_reply[:500] if latest_reply else "执行已完成，未提供详细摘要。"

    criteria_block = ""
    criteria = getattr(task, "acceptance_criteria", None)
    if criteria and isinstance(criteria, list) and criteria:
        criteria_lines = "\n".join(f"- {c}" for c in criteria)
        criteria_block = f"【验收基准】\n{criteria_lines}\n\n"

    import os
    from datetime import datetime, timezone

    deliverables_block = ""
    file_refs = [r for r in refs if r.get("type") in ("file", "image", "artifact")]
    if file_refs:
        paths = []
        for r in file_refs:
            target = r.get("target_id") or ""
            name = r.get("name") or "交付物"
            fp_info = ""
            if target and os.path.isfile(target):
                try:
                    sz = os.path.getsize(target)
                    mtime = datetime.fromtimestamp(os.path.getmtime(target), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    fp_info = f" (大小: {sz} 字节, 修改时间: {mtime})"
                except Exception:
                    pass
            paths.append(f"- {name}: {target}{fp_info}")
        deliverables_block = f"【交付产物清单与物理指纹（请使用 view_file 等只读工具核查）】\n" + "\n".join(paths) + "\n\n"

    # 执行现场快照（时间窗 + 自检证据数值锚点）
    start_time = task.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if getattr(task, "created_at", None) else "未知"
    end_time = task.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if getattr(task, "updated_at", None) else "未知"
    snapshot_lines = [f"- 执行时间窗: {start_time} 至 {end_time}"]

    self_check = getattr(task, "self_check", None)
    if isinstance(self_check, dict):
        checks = self_check.get("checks") or []
        evidence_lines = []
        for c in checks:
            if isinstance(c, dict) and c.get("evidence"):
                mark = "✓" if c.get("pass") else "✗"
                c_name = c.get("name") or c.get("title") or "检查项"
                evidence_lines.append(f"  * {mark} {c_name}: {c.get('evidence')}")
        if evidence_lines:
            snapshot_lines.append("- 执行者自检证据数值锚点:\n" + "\n".join(evidence_lines))
        if self_check.get("deviations"):
            snapshot_lines.append(f"- 偏差说明: {self_check.get('deviations')}")

    snapshot_block = f"【执行现场快照】\n" + "\n".join(snapshot_lines) + "\n\n"

    content = (
        f"[值守系统代用户] 任务 {label}「{title}」已由值守执行完成，请核验交付结果。\n\n"
        f"【执行交付简报】\n"
        f"{result_summary}\n\n"
        f"{criteria_block}"
        f"{snapshot_block}"
        f"{deliverables_block}"
        f"请你以我的立场评审核实该任务的完成情况（只评审，不实施；不要修改任何数据、"
        f"不要执行任何写操作，可通过只读文件工具查验关联交付物与执行记录）：\n"
        f"1) 回顾本对话中我最初提出这件事的意图与预期，以我的原始表述为准，"
        f"不要以执行报告的自我描述为准；\n"
        f"2) 对照执行者的交付简报、自检证据数值与关联产物，逐条核对目标是否达成；关键数据要交叉验证；\n"
        f"3) 有无遗漏、漂移或只完成了一部分的迹象；\n"
        f"4) 评审意见中请在首行或末尾注明评审时点（校准环境漂移）。\n\n"
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
        references=refs or None,
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


async def latest_reviewer_reply(thread_id: str) -> str:
    """从落库消息里取评审者最后一条 ai 回复。

    SESSION_COMPLETED 的内存 summary 存在与消息落库的竞态窗口（评审回复
    已落库但 summary 未含结论行曾致"无结论=不通过"误判，两轮烧完转仲裁）。
    verdict 判定必须以落库事实为准：优先 summary，无结论行时回退本函数。
    """
    return await _latest_ai_reply(thread_id, assistant_categories_only=False)


async def _latest_reviewer_message_id(thread_id: str) -> str | None:
    """评审者最后一条 ai 消息的 id（与 _latest_ai_reply 同条件同排序）。"""
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.conversation import Message

    async with session_scope() as session:
        stmt = (
            select(Message.id)
            .where(
                Message.thread_id == thread_id,
                Message.role == "ai",
                Message.content.isnot(None),
                Message.content != "",
            )
            .order_by(Message.sequence_number.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar()
        return str(row) if row else None


async def _annotate_reviewer_message(
    task, verdict: str, feedback: str, message_id: str | None
) -> None:
    """把评审结论结构化挂到评审回复消息上（Chat→Canvas 互链的数据源）。

    前端在消息气泡下渲染 TaskStateChip（#T-x + 结论 + 跳画布），点击经
    sessionStorage("duty:focus-task") 一次性交接给值守画布 flyToCard。
    """
    if not message_id:
        return
    try:
        from datetime import datetime, timezone

        from app.infrastructure.database import session_scope
        from app.models.conversation import Message

        async with session_scope() as session:
            msg = await session.get(Message, message_id)
            if msg is None:
                return
            meta = dict(msg.meta_data or {})
            meta["duty_task"] = {
                "task_id": str(task.id),
                "task_no": task_number(task),
                "task_title": task_title(task) or "",
                "verdict": verdict,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            if feedback:
                meta["duty_task"]["feedback"] = feedback[:200]
            msg.meta_data = meta
            session.add(msg)
    except Exception as e:
        logger.warning("[TaskReview] annotate reviewer message failed: %s", e)


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
    # Chat→Canvas 互链：把结论结构化挂到评审回复消息（TaskStateChip 数据源）
    await _annotate_reviewer_message(
        task,
        verdict,
        feedback,
        await _latest_reviewer_message_id(getattr(task, "origin_thread_id", "") or ""),
    )
