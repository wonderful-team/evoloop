"""In-memory batch approval grants for intent-level HITL.

WARNING: This is a POC implementation. Grants are stored in process memory and
will be lost on service restart. For production use, persist grants to the
database (e.g., a ``batch_approval_grants`` table) with TTL management.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BatchOperation:
    """A single operation covered by a batch approval grant."""

    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    macro_id: int | None = None
    macro_name: str | None = None
    description: str | None = None


@dataclass
class BatchGrant:
    """A batch approval grant covering one or more operations."""

    id: str
    thread_id: str
    request_id: str
    operations: list[BatchOperation]
    status: str  # pending, approved, expired
    expires_at: datetime


# In-memory registry keyed by grant_id.
_grants: dict[str, BatchGrant] = {}


def _clean_expired() -> None:
    now = datetime.now(timezone.utc)
    for grant_id, grant in list(_grants.items()):
        if grant.expires_at < now:
            grant.status = "expired"
            _grants.pop(grant_id, None)


def create_pending_grant(
    grant_id: str,
    thread_id: str,
    request_id: str,
    operations: list[dict[str, Any]],
    ttl_seconds: int = 300,
) -> BatchGrant:
    """Create a pending batch grant from a list of raw operation dicts."""
    _clean_expired()
    parsed_ops: list[BatchOperation] = []
    for op in operations:
        parsed_ops.append(
            BatchOperation(
                tool_name=op.get("tool_name", ""),
                params=op.get("params") or {},
                macro_id=op.get("macro_id"),
                macro_name=op.get("macro_name"),
                description=op.get("description"),
            )
        )
    grant = BatchGrant(
        id=grant_id,
        thread_id=thread_id,
        request_id=request_id,
        operations=parsed_ops,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    )
    _grants[grant_id] = grant
    logger.info(
        "[BatchGrant] Created pending grant=%s thread=%s operations=%d expires=%s",
        grant_id,
        thread_id,
        len(parsed_ops),
        grant.expires_at.isoformat(),
    )
    return grant


def update_grant_request_id(grant_id: str, request_id: str) -> bool:
    """Link a pending grant to the HITL request created after it."""
    grant = _grants.get(grant_id)
    if grant and grant.status == "pending":
        grant.request_id = request_id
        return True
    return False


def approve_grant_by_request_id(request_id: str) -> BatchGrant | None:
    """Approve the pending grant associated with the given HITL request_id."""
    for grant in _grants.values():
        if grant.request_id == request_id and grant.status == "pending":
            grant.status = "approved"
            logger.info(
                "[BatchGrant] Approved grant=%s request_id=%s operations=%d",
                grant.id,
                request_id,
                len(grant.operations),
            )
            return grant
    return None


def reject_grant_by_request_id(request_id: str) -> BatchGrant | None:
    """Mark the pending grant associated with the given HITL request_id as expired."""
    for grant in _grants.values():
        if grant.request_id == request_id and grant.status == "pending":
            grant.status = "expired"
            logger.info(
                "[BatchGrant] Rejected grant=%s request_id=%s",
                grant.id,
                request_id,
            )
            return grant
    return None


def _normalize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Strip runtime-injected keys that should not affect grant matching.

    Runtime-injected keys（下划线前缀，或工具执行环境注入的上下文参数）只影响
    执行方式、不改变操作对象，匹配时应忽略。
    """
    if not params:
        return {}
    return {
        k: v for k, v in params.items() if not k.startswith("_") and k != "base_url"
    }


def is_operation_granted(
    thread_id: str,
    tool_name: str,
    params: dict[str, Any] | None = None,
    macro_id: int | None = None,
) -> bool:
    """Check whether the current operation is covered by an approved batch grant."""
    _clean_expired()
    now = datetime.now(timezone.utc)
    call_params = _normalize_params(params)
    for grant in list(_grants.values()):
        if grant.status != "approved":
            continue
        if grant.expires_at < now:
            grant.status = "expired"
            continue
        if grant.thread_id != thread_id:
            continue
        for op in grant.operations:
            if op.tool_name != tool_name:
                continue
            if (
                macro_id is not None
                and op.macro_id is not None
                and op.macro_id != macro_id
            ):
                continue
            op_params = _normalize_params(op.params)
            if op_params == call_params:
                logger.info(
                    "[BatchGrant] Operation covered by grant=%s tool=%s macro_id=%s",
                    grant.id,
                    tool_name,
                    macro_id,
                )
                return True
    return False


def revoke_grant(grant_id: str) -> bool:
    """Explicitly revoke a batch grant by id."""
    grant = _grants.pop(grant_id, None)
    if grant:
        grant.status = "expired"
        logger.info("[BatchGrant] Revoked grant=%s", grant_id)
        return True
    return False
