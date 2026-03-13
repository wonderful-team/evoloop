"""
Cloud Agent API - Centralized LangGraph Agent for client devices.

Client sends execution requests here when local decision-making
requires cloud intelligence or LTM context.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Literal

from app.api.deps import verify_device_token
from app.logging import logger

router = APIRouter()


class AgentRequest(BaseModel):
    """Request from client device for cloud agent processing."""
    device_id: str
    session_id: str
    intent: str = Field(description="User's high-level intent")
    context: dict[str, Any] = Field(default_factory=dict)
    local_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Current state from local execution"
    )
    request_type: Literal["plan", "decide", "reflect"] = "plan"


class AgentResponse(BaseModel):
    """Response from cloud agent to client device."""
    session_id: str
    decision: dict[str, Any]
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: str | None = None
    ltm_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Relevant LTM memories for this decision"
    )


class ToolResultRequest(BaseModel):
    """Client reports tool execution results to agent."""
    device_id: str
    session_id: str
    tool_call_id: str
    result: dict[str, Any]
    success: bool
    error: str | None = None


@router.post("/plan", response_model=AgentResponse)
async def agent_plan(
    request: AgentRequest,
    _: str = Depends(verify_device_token)
) -> AgentResponse:
    """
    Request a plan from the cloud agent.

    Client sends intent and local context, cloud agent:
    1. Queries LTM for relevant memories
    2. Builds execution plan using LangGraph
    3. Returns plan + any cloud-side tool needs
    """
    logger.info(f"[CloudAgent] Plan request from device {request.device_id}: {request.intent}")

    # TODO: Integrate with actual LangGraph agent
    # For now, return mock response
    return AgentResponse(
        session_id=request.session_id,
        decision={
            "action": "execute_macro",
            "macro_id": "example_macro",
            "steps": [
                {"type": "navigate", "target": "home"},
                {"type": "click", "target": "button_login"},
            ]
        },
        tool_calls=[],
        reasoning="Planned based on user intent and LTM patterns",
        ltm_context={
            "similar_executions": 3,
            "success_rate": 0.95
        }
    )


@router.post("/decide", response_model=AgentResponse)
async def agent_decide(
    request: AgentRequest,
    _: str = Depends(verify_device_token)
) -> AgentResponse:
    """
    Request a decision from cloud agent during execution.

    Used when local agent encounters anomaly and needs
    cloud intelligence to decide next action.
    """
    logger.info(f"[CloudAgent] Decide request from device {request.device_id}")

    # TODO: Integrate with actual LangGraph agent
    return AgentResponse(
        session_id=request.session_id,
        decision={"action": "continue", "adaptation": None},
        tool_calls=[],
        reasoning="Continue with current approach",
        ltm_context={}
    )


@router.post("/reflect")
async def agent_reflect(
    request: AgentRequest,
    _: str = Depends(verify_device_token)
) -> dict[str, Any]:
    """
    Request post-execution reflection from cloud agent.

    Client sends execution trace, cloud agent:
    1. Analyzes success/failure patterns
    2. Updates LTM with learnings
    3. Returns insights for local adaptation
    """
    logger.info(f"[CloudAgent] Reflect request from device {request.device_id}")

    return {
        "session_id": request.session_id,
        "reflection": {
            "success": True,
            "patterns_observed": ["quick_completion"],
            "suggestions": []
        },
        "ltm_updated": True
    }


@router.post("/tool-result")
async def report_tool_result(
    request: ToolResultRequest,
    _: str = Depends(verify_device_token)
) -> dict[str, Any]:
    """
    Client reports tool execution results.

    Allows cloud agent to continue reasoning with
    actual execution outcomes.
    """
    logger.info(
        f"[CloudAgent] Tool result from {request.device_id}: "
        f"{request.tool_call_id} success={request.success}"
    )

    return {
        "session_id": request.session_id,
        "acknowledged": True,
        "next_action": "continue"
    }
