"""In-session task handover for workflow pipelines (原任务会话内交接清单生成)."""

import asyncio
import logging

from app.domain.tasks.service import (
    task_last_result,
    task_number,
    task_title,
)

logger = logging.getLogger(__name__)

HANDOVER_PROMPT = (
    "【值守系统交接指引】本任务已通过评审验收。检测到流水线中存在下游任务依赖本任务的产出，"
    "请为下游提供结构化【交付交接清单】：\n"
    "1. 核心产物文件与绝对路径；\n"
    "2. 数据结构契约与核心字段说明（若产生 JSON / CSV / 数据集）；\n"
    "3. 核心执行脚本与函数入口（若生成或修改了 Python 脚本）；\n"
    "4. 留给下游任务的执行建议与注意事项。\n"
    "（请直接输出清晰精炼的 Markdown 清单，无需再调用任何工具）"
)

HANDOVER_TIMEOUT_SECONDS = 35.0


async def generate_in_session_handover(task) -> str | None:
    """在原执行会话 (last_thread_id) 追发一条交接指引，由 Agent 生成交付交接清单。

    - 仅对有下游依赖项的任务触发；
    - 复用执行者原线程（热上下文，无幻觉，零额外外围 Prompt）；
    - 带超时（35s）与异常捕获，失败自动降级返回 None，绝不阻塞任务终态。
    """
    thread_id = getattr(task, "last_thread_id", None)
    if not thread_id:
        logger.info("[TaskHandover] task %s has no last_thread_id; skipping", task.id)
        return None

    from app.core.engine.agent import run_agent_background
    from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
    from app.domain.tasks.review import _latest_executor_reply
    from app.domain.tasks.service import TaskQueueService

    try:
        member_id = await TaskQueueService.resolve_member_id(task)
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=HANDOVER_PROMPT,
            project_id=task.project_id,
            member_id=member_id,
            metadata={
                "source": "task_handover",
                "source_task_id": task.id,
                "channel_name": "",
            },
        )
        if result.status == DispatchStatus.FAILED or not result.inputs:
            logger.warning(
                "[TaskHandover] dispatch handover prompt failed for task %s: %s",
                task.id,
                result.error,
            )
            return None

        # 执行单轮生成，超时保护
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs),
            timeout=HANDOVER_TIMEOUT_SECONDS,
        )

        reply = await _latest_executor_reply(thread_id)
        summary = (reply or "").strip()
        if summary:
            logger.info(
                "[TaskHandover] successfully generated handover summary for task %s (%d chars)",
                task.id,
                len(summary),
            )
            return summary
        return None
    except asyncio.TimeoutError:
        logger.warning(
            "[TaskHandover] timeout (%.1fs) generating handover for task %s; falling back",
            HANDOVER_TIMEOUT_SECONDS,
            task.id,
        )
        return None
    except Exception as e:
        logger.warning(
            "[TaskHandover] error generating handover for task %s: %s", task.id, e
        )
        return None
