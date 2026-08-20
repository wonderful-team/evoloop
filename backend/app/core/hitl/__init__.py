"""HITL (Human-in-the-Loop) and authorization framework."""

from app.core.hitl.authorization import AuthorizationDecision, AuthorizationService
from app.core.hitl.core import (
    HumanInputRequest,
    cancel_request,
    create_request,
    finalize_request,
    get_pending_requests_for_thread,
    push_hitl_notification,
    raise_hitl_interrupt,
)
from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.hitl.policies import (
    DEFAULT_SENSITIVE_PATTERNS,
    AuthorizationPolicy,
    GrantedPermission,
    PolicyLoader,
)
from app.core.hitl.prompts import build_approval_context, format_risk_header

__all__ = [
    "HumanInputRequest",
    "create_request",
    "cancel_request",
    "finalize_request",
    "get_pending_requests_for_thread",
    "push_hitl_notification",
    "raise_hitl_interrupt",
    "HITLOrchestrator",
    "build_approval_context",
    "format_risk_header",
    "AuthorizationPolicy",
    "GrantedPermission",
    "PolicyLoader",
    "DEFAULT_SENSITIVE_PATTERNS",
    "AuthorizationDecision",
    "AuthorizationService",
]
