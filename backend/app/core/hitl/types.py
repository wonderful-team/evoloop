"""HITL 类型与枚举定义（叶子模块，仅依赖标准库）。

HITL 类型同时被以下子系统消费，作为双方共享的契约：
- ``app.core.hitl``：请求生命周期（create/resume/finalize）的校验；
- ``app.core.monitoring``：向前端推送 HITL 通知时的 payload 类型。

保持本模块为叶子（不 import 任何 app 模块），monitoring → hitl 是合法
单向依赖（观测领域类型）。
"""

from enum import Enum


class HumanRequestType(str, Enum):
    """Types of human requests that backend can make."""

    # Traditional text input
    TEXT = "text"
    """Request text input from user (traditional HITL)."""

    # Project-related
    PROJECT_SWITCH = "project_switch"
    """Request user to switch to a specific project or select from list."""

    # Confirmation
    CONFIRMATION = "confirmation"
    """Request yes/no confirmation from user."""

    # Approval
    APPROVAL = "approval"
    """Request explicit approval for impactful actions."""

    # File selection
    FILE_SELECT = "file_select"
    """Request user to select one or more files."""

    # Single Choice
    CHOICE = "choice"
    """Request user to select a single option from a list."""

    # Multi Choice
    MULTI_CHOICE = "multi_choice"
    """Request user to select multiple options from a list.

    运营可勾选多项；resume 时以逗号分隔的字符串原样回传给 Agent，
    由 Agent 解析后只执行被选中的部分。
    """


class RiskLevel(str, Enum):
    """HITL 审批/操作风险等级（与 RISK_EMOJI 展示键保持一致）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HITLDecision(str, Enum):
    """审批决策令牌：normalize 输出与结果判定统一使用。"""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class HITLRequestStatus(str, Enum):
    """human_requests / messages 双轨状态。"""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
