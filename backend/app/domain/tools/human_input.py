"""
Human-in-the-Loop Tools for Agent collaboration with users.
Enables the agent to pause execution, request user input, and seek approval for actions.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Literal, List, Any
from uuid import uuid4

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from app.core.monitoring.activity import activity_monitor

logger = logging.getLogger("evoloop.tools.human_input")


# ============ Data Models ============

class HumanInputRequest(BaseModel):
    """Stored request for human input."""
    id: str
    thread_id: str
    request_type: Literal["text", "choice", "confirmation", "approval"]
    prompt: str
    options: Optional[List[str]] = None
    context: Optional[str] = None
    default_value: Optional[str] = None
    timeout_seconds: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["pending", "completed", "timeout", "cancelled"] = "pending"
    response: Optional[Any] = None


# In-memory store for pending requests
# In production, this should be stored in database for persistence across restarts
_pending_requests: dict[str, HumanInputRequest] = {}


# ============ Input Schemas ============

class RequestHumanInputArgs(BaseModel):
    prompt: str = Field(..., description="The question or instruction to present to the user.")
    input_type: Literal["text", "choice", "confirmation"] = Field(
        "text",
        description="Type of input: 'text' for free-form, 'choice' for selection, 'confirmation' for yes/no."
    )
    options: Optional[List[str]] = Field(
        None,
        description="Required if input_type is 'choice'. List of options for user to select from."
    )
    context: Optional[str] = Field(
        None,
        description="Additional context to help the user understand what's needed."
    )
    default_value: Optional[str] = Field(
        None,
        description="Default value if user doesn't respond within timeout."
    )


class RequestApprovalArgs(BaseModel):
    action_description: str = Field(
        ..., 
        description="Clear description of the action that requires approval."
    )
    risk_level: Literal["low", "medium", "high", "critical"] = Field(
        "medium",
        description="Risk level of the action to help user make informed decision."
    )
    details: Optional[str] = Field(
        None,
        description="Detailed information about what will happen if approved."
    )
    consequences: Optional[str] = Field(
        None,
        description="Potential consequences or impact of this action."
    )


# ============ Core Request Management ============

def create_request(
    thread_id: str,
    request_type: str,
    prompt: str,
    options: Optional[List[str]] = None,
    context: Optional[str] = None,
    default_value: Optional[str] = None,
    timeout_seconds: Optional[int] = 300
) -> HumanInputRequest:
    """Create and store a human input request."""
    request = HumanInputRequest(
        id=str(uuid4()),
        thread_id=thread_id,
        request_type=request_type,
        prompt=prompt,
        options=options,
        context=context,
        default_value=default_value,
        timeout_seconds=timeout_seconds
    )
    _pending_requests[request.id] = request
    logger.info(f"Created human input request: {request.id} ({request_type})")
    return request


def get_pending_request(request_id: str) -> Optional[HumanInputRequest]:
    """Get a pending request by ID."""
    return _pending_requests.get(request_id)


def get_pending_requests_for_thread(thread_id: str) -> List[HumanInputRequest]:
    """Get all pending requests for a specific thread."""
    return [
        req for req in _pending_requests.values()
        if req.thread_id == thread_id and req.status == "pending"
    ]


def complete_request(request_id: str, response: Any) -> bool:
    """Complete a pending request with user's response."""
    if request_id not in _pending_requests:
        return False
    
    request = _pending_requests[request_id]
    request.status = "completed"
    request.response = response
    logger.info(f"Completed human input request: {request_id} with response: {response}")
    return True


def cancel_request(request_id: str) -> bool:
    """Cancel a pending request."""
    if request_id not in _pending_requests:
        return False
    
    request = _pending_requests[request_id]
    request.status = "cancelled"
    logger.info(f"Cancelled human input request: {request_id}")
    return True


# ============ Tools ============

@tool("request_human_input", args_schema=RequestHumanInputArgs)
async def request_human_input(
    prompt: str,
    input_type: Literal["text", "choice", "confirmation"] = "text",
    options: Optional[List[str]] = None,
    context: Optional[str] = None,
    default_value: Optional[str] = None
) -> str:
    """
    Pause execution and request input from the user.
    
    Use this tool when you:
    - Need information that only the user can provide
    - Require clarification on requirements
    - Want user to make a decision between options
    - Need confirmation before proceeding
    
    The workflow will pause until the user responds.
    
    Returns the user's response as a string.
    """
    from app.utils.context import get_context
    
    try:
        ctx = get_context()
        thread_id = ctx.get("thread_id", "unknown")
    except:
        thread_id = "unknown"
    
    # Validate choice options
    if input_type == "choice" and not options:
        return "Error: 'options' must be provided when input_type is 'choice'"
    
    # Create the request
    request = create_request(
        thread_id=thread_id,
        request_type=input_type,
        prompt=prompt,
        options=options,
        context=context,
        default_value=default_value
    )
    
    # Format response for the agent
    # The actual waiting/response handling is done by the frontend + API layer
    response_text = f"""
## ⏸️ Human Input Requested

**Request ID**: `{request.id}`
**Type**: {input_type}
**Prompt**: {prompt}
"""
    
    if context:
        response_text += f"\n**Context**: {context}\n"
    
    if options:
        response_text += f"\n**Options**: {', '.join(options)}\n"
    
    if default_value:
        response_text += f"\n**Default**: {default_value}\n"
    
    response_text += """
---
⚠️ **Workflow paused**. Waiting for user response.
The frontend will display this request and collect user input.
"""
    
    logger.info(f"Human input requested: {prompt[:50]}...")
    
    # Notify Activity Monitor with Structured Data
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data={
            "id": request.id,
            "type": input_type,
            "prompt": prompt,
            "options": options,
            "context": context,
            "default_value": default_value,
            "timeout_seconds": 300
        }
    )
    
    return response_text


@tool("request_approval", args_schema=RequestApprovalArgs)
async def request_approval(
    action_description: str,
    risk_level: Literal["low", "medium", "high", "critical"] = "medium",
    details: Optional[str] = None,
    consequences: Optional[str] = None
) -> str:
    """
    Request user approval before executing a potentially impactful action.
    
    Use this tool before:
    - Deleting or modifying important files
    - Running commands that could have side effects
    - Making irreversible changes
    - Executing operations with significant cost
    
    The workflow will pause until the user approves or rejects.
    
    Returns "APPROVED" or "REJECTED" based on user decision.
    """
    from app.utils.context import get_context
    
    try:
        ctx = get_context()
        thread_id = ctx.get("thread_id", "unknown")
    except:
        thread_id = "unknown"
    
    # Build approval context
    risk_emoji = {
        "low": "🟢",
        "medium": "🟡", 
        "high": "🟠",
        "critical": "🔴"
    }
    
    approval_context = f"""
{risk_emoji.get(risk_level, '⚪')} **Risk Level**: {risk_level.upper()}

**Action**: {action_description}
"""
    
    if details:
        approval_context += f"\n**Details**:\n{details}\n"
    
    if consequences:
        approval_context += f"\n**Potential Consequences**:\n{consequences}\n"
    
    # Create the request
    request = create_request(
        thread_id=thread_id,
        request_type="approval",
        prompt=action_description,
        context=approval_context,
        default_value="REJECTED"  # Default to safe option
    )
    
    response_text = f"""
## 🔐 Approval Required

**Request ID**: `{request.id}`
{approval_context}
---
⚠️ **Workflow paused**. Awaiting user approval.
Please respond with APPROVE or REJECT.
"""
    
    logger.info(f"Approval requested for: {action_description[:50]}... (Risk: {risk_level})")
    
    # Notify Activity Monitor with Structured Data
    await activity_monitor.set_human_request(
        thread_id=thread_id,
        request_data={
            "id": request.id,
            "type": "approval",
            "prompt": action_description,
            "context": approval_context,
            "default_value": "REJECTED",
            "risk_level": risk_level
        }
    )
    
    return response_text


# ============ API Helpers ============

def get_all_pending_requests() -> List[dict]:
    """Get all pending requests as dictionaries (for API responses)."""
    return [
        {
            "id": req.id,
            "thread_id": req.thread_id,
            "request_type": req.request_type,
            "prompt": req.prompt,
            "options": req.options,
            "context": req.context,
            "default_value": req.default_value,
            "created_at": req.created_at.isoformat(),
            "status": req.status
        }
        for req in _pending_requests.values()
        if req.status == "pending"
    ]


def cleanup_old_requests(max_age_hours: int = 24):
    """Remove old completed/cancelled requests."""
    cutoff = datetime.utcnow()
    to_remove = []
    
    for req_id, req in _pending_requests.items():
        if req.status in ("completed", "cancelled", "timeout"):
            age = (cutoff - req.created_at).total_seconds() / 3600
            if age > max_age_hours:
                to_remove.append(req_id)
    
    for req_id in to_remove:
        del _pending_requests[req_id]
    
    if to_remove:
        logger.info(f"Cleaned up {len(to_remove)} old human input requests")
