"""Todo facade tool — single unified entry (OpenCode `todo`/todowrite semantic, §10.2.2).

把 create/list/complete/cancel 四件套收敛为一次调用按 ``action`` 分发；
``set`` 动作在当前会话（source_conversation_id）内做全量重写：不在新列表中的
pending todo 自动取消，缺失的自动创建（不影响其它会话/用户的任务）。
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.domain.todo.constants import DEFAULT_TODO_LIMIT
from app.domain.todo.formatting import format_todo_list
from app.domain.todo.schemas import TodoCreate, TodoFilter
from app.domain.todo.service import TodoNotFoundError, TodoService
from app.domain.todo.utils import parse_due_date
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoPriority, TodoStatus

logger = logging.getLogger(__name__)


@evoloop_tool(
    name="todo",
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.todo",
)
async def todo(
    action: Literal["list", "create", "complete", "cancel", "set"] = "list",
    title: str | None = None,
    description: str | None = None,
    due_date: str | None = None,
    priority: Literal["low", "medium", "high"] = TodoPriority.MEDIUM,
    status: Literal["pending", "completed", "cancelled"] | None = None,
    todo_id: str | None = None,
    items: list[str] | None = None,
    limit: int = DEFAULT_TODO_LIMIT,
    project_id: int | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一待办管理（对齐 OpenCode todowrite 语义）。

    Actions:
    - list:   查看待办（可按 status 过滤）。
    - create: 新建一条待办。
    - complete / cancel: 按 todo_id 完结/取消一条待办。
    - set:    全量重写当前会话的待办列表（items 为期望的完整标题列表）——不在列表中的
              pending 待办自动取消，缺失的自动创建。

    WHEN TO USE:
    - 用户说"提醒我/记得做/待办清单"。
    - 长任务（跑测试/部署）进行中创建 todo 让用户知道回头检查。
    - 更新整体待办进度时优先用 set 一次同步全量列表。

    Args:
        action: 执行的动作（list / create / complete / cancel / set）。
        title: create 时必填的待办标题。
        description: create 时的详细描述。
        due_date: create 时的截止时间（ISO / 相对时间 / 中文）。
        priority: create 时的优先级。
        status: list 时的过滤条件。
        todo_id: complete / cancel 时必填的待办 ID。
        items: set 时期望的完整待办标题列表（全量重写）。
        limit: list 时的最大条数。
        project_id: 可选的项目 ID。
    """
    thread_id = config.get("configurable", {}).get("thread_id") if config else None
    run_id = config.get("metadata", {}).get("run_id") if config else None

    async with session_scope() as session:
        service = TodoService(session)

        if action == "list":
            filter_status = TodoStatus(status) if status else None
            todos = await service.list_todos(
                TodoFilter(status=filter_status, project_id=project_id, limit=limit)
            )
            if not todos:
                return i18n.get("domain_tools.manage_todo.no_todos")
            return format_todo_list(todos, title="Todo List"), {"count": len(todos)}

        if action == "create":
            if not title:
                return i18n.get("domain_tools.manage_todo.error_title")
            parsed = parse_due_date(due_date)
            if due_date and parsed is None:
                return i18n.get("domain_tools.manage_todo.error_due_date", date=due_date)
            todo_obj = await service.create(
                data=TodoCreate(
                    title=title,
                    description=description,
                    due_date=due_date,
                    priority=priority,
                    project_id=project_id,
                ),
                source_conversation_id=thread_id,
                run_id=run_id,
            )
            return i18n.get(
                "domain_tools.manage_todo.success_add",
                priority=todo_obj.priority.value.upper(),
                title=todo_obj.title,
                id=todo_obj.id,
            ), {"id": todo_obj.id}

        if action in ("complete", "cancel"):
            if not todo_id:
                return i18n.get("domain_tools.manage_todo.error_id", action=action)
            try:
                if action == "complete":
                    todo_obj = await service.mark_completed(todo_id)
                else:
                    todo_obj = await service.mark_cancelled(todo_id)
                return i18n.get(
                    "domain_tools.manage_todo.success_update", id=todo_obj.id
                ) + f" [{todo_obj.status.value}] {todo_obj.title}", {
                    "id": todo_obj.id,
                    "status": todo_obj.status.value,
                }
            except TodoNotFoundError:
                return i18n.get("domain_tools.manage_todo.error_not_found", id=todo_id)

        if action == "set":
            # 全量重写：仅影响当前会话创建的 pending todo。
            if not thread_id:
                return "Error: set 需要会话上下文（thread_id）。"
            expected = [str(t).strip() for t in (items or []) if str(t).strip()]
            pending = await service.list_todos(
                TodoFilter(
                    status=TodoStatus.PENDING,
                    project_id=project_id,
                    limit=1000,
                )
            )
            session_todos = [
                t for t in pending if t.source_conversation_id == thread_id
            ]
            created, cancelled = [], []
            existing_titles = {t.title.strip().lower(): t for t in session_todos}
            for title_text in expected:
                if title_text.lower() not in existing_titles:
                    todo_obj = await service.create(
                        data=TodoCreate(title=title_text, project_id=project_id),
                        source_conversation_id=thread_id,
                        run_id=run_id,
                    )
                    created.append(todo_obj.title)
                else:
                    existing_titles.pop(title_text.lower())
            for leftover in existing_titles.values():
                await service.mark_cancelled(leftover.id)
                cancelled.append(leftover.title)
            return (
                f"Todo list rewritten: created {len(created)}, cancelled {len(cancelled)}."
                + (f"\nCreated: {', '.join(created)}" if created else "")
                + (f"\nCancelled: {', '.join(cancelled)}" if cancelled else ""),
                {"created": len(created), "cancelled": len(cancelled)},
            )

        return f"Error: unknown todo action '{action}'."
