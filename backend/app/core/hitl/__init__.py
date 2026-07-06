"""HITL (Human-in-the-Loop) and authorization framework."""

from app.core.hitl.authorization import AuthorizationDecision, AuthorizationService
from app.core.hitl.core import (
    HumanInputRequest,
    cancel_request,
    cleanup_old_requests,
    complete_request,
    create_request,
    get_all_pending_requests,
    get_pending_request,
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

__all__ = [
    "HumanInputRequest",
    "create_request",
    "complete_request",
    "cancel_request",
    "get_pending_request",
    "get_pending_requests_for_thread",
    "get_all_pending_requests",
    "cleanup_old_requests",
    "push_hitl_notification",
    "raise_hitl_interrupt",
    "HITLOrchestrator",
    "AuthorizationPolicy",
    "GrantedPermission",
    "PolicyLoader",
    "DEFAULT_SENSITIVE_PATTERNS",
    "AuthorizationDecision",
    "AuthorizationService",
]
