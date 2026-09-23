"""队列任务 API 请求体强类型（/tasks/queue 的 POST/PUT body 契约）。

此前为裸 dict[str, Any]：无字段校验、OpenAPI 无真实形状（审计 P1-12）。
请求体自此强类型；响应保持既有扁平形状（前端手写客户端的既有契约，
信封化按 docs/api-response-envelope.md 渐进式推进，不在此强改）。
"""

from datetime import datetime
from enum import Enum

from app.infrastructure.pydantic_base import DynamicBaseModel


class TaskPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskRiskLevel(str, Enum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


class TaskType(str, Enum):
    ONCE = "once"
    RECURRING = "recurring"


class TaskCreateRequest(DynamicBaseModel):
    """POST /tasks/queue — 用户建任务（看板表单 / 提案确认后的正式任务）。"""

    title: str
    description: str = ""
    type: TaskType = TaskType.ONCE
    project_id: int = 0
    category: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    risk_level: TaskRiskLevel | None = None
    # recurring 必填 trigger_spec（cron 或 interval:秒）——服务端二次校验
    trigger_spec: str | None = None
    due_at: datetime | None = None
    parent_id: str | None = None
    dependencies: list[str] | None = None


class TaskEditRequest(DynamicBaseModel):
    """PUT /tasks/queue/{id} — 字段编辑 + 取消（status=cancelled）。

    全字段可选（PATCH 语义）：None = 不改；clear_* 显式清空。
    """

    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    risk_level: TaskRiskLevel | None = None
    type: TaskType | None = None
    due_at: datetime | None = None
    clear_due_at: bool = False
    trigger_spec: str | None = None
    clear_trigger_spec: bool = False
    dependencies: list[str] | None = None
    # 唯一合法的状态写入：取消（其余状态转移全部系统驱动）。
    # cancel 是 status="cancelled" 的布尔简写（既有前端契约）
    status: str | None = None
    cancel: bool = False
