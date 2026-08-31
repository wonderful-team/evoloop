"""HITL 工具参数 Schema（ask_human / ask_confirm 的入参契约）。

从 ``app.domain.tools.schemas`` 收编而来，与 ``app.core.hitl.tools`` 同属
HITL 子系统，避免 hitl 反向依赖 domain。
"""

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
