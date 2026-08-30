"""HITL 工具参数 Schema（ask_human / ask_confirm 的入参契约）。

从 ``app.domain.tools.schemas`` 收编而来，与 ``app.core.hitl.tools`` 同属
HITL 子系统，避免 hitl 反向依赖 domain。
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.hitl.types import HumanRequestType, RiskLevel


class RequestHumanInputArgs(BaseModel):
    prompt: str = Field(
        ..., description="The question or instruction to present to the user."
    )
    input_type: HumanRequestType = Field(
        HumanRequestType.TEXT,
        description="Type of input: 'text' for free-form, 'choice' for single selection, 'multi_choice' for multi-select (comma-separated result), 'confirmation' for yes/no.",
    )
    options: list[str] | None = Field(
        None,
        description="Required if input_type is 'choice' or 'multi_choice'. List of options for user to select from.",
    )
    context: str | None = Field(
        None,
        description="Additional context to help the user understand what's needed.",
    )
    default_value: str | None = Field(
        None, description="Default value if user doesn't respond within timeout."
    )


class BatchOperationItem(BaseModel):
    """Single operation included in a batch approval request."""

    tool_name: str = Field(
        ...,
        description="Tool to execute, e.g. 'run_macro' or 'mcp__mall__agree_refund'.",
    )
    macro_id: int | None = Field(
        None,
        description="Macro ID when tool_name is 'run_macro'.",
    )
    macro_name: str | None = Field(
        None,
        description="Macro name (human-readable).",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Business parameters for this operation.",
    )
    description: str | None = Field(
        None,
        description="Human-readable description shown in the approval card.",
    )


class RequestApprovalArgs(BaseModel):
    action_description: str = Field(
        ..., description="Clear description of the action that requires approval."
    )
    risk_level: RiskLevel = Field(
        RiskLevel.MEDIUM,
        description="Risk level of the action to help user make informed decision.",
    )
    details: str | None = Field(
        None, description="Detailed information about what will happen if approved."
    )
    consequences: str | None = Field(
        None, description="Potential consequences or impact of this action."
    )
    operations: list[BatchOperationItem] | None = Field(
        None,
        description=(
            "Optional batch operation list. When provided, this is a batch approval: "
            "the user approves/disapproves the entire list at once, and approved "
            "operations bypass per-call confirmation for the grant window. "
            "Each entry must include tool_name and the exact business parameters."
        ),
    )
    risk_note: str | None = Field(
        None,
        description="Risk explanation for batch approvals (why bulk execution is acceptable or what to watch).",
    )
