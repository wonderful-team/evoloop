"""Authorization framework for project-level resource access control.

The core policy evaluation has been moved to ``app.core.security.authorization``.
This module now acts as a thin HITL-facing wrapper: it uses the evaluator to
decide whether a tool invocation is allowed, and when approval is required it
delegates to ``HITLOrchestrator.request_authorization()`` which raises
``AgentHumanInterruptException``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.hitl.constants import DEFAULT_AUTHORIZATION_TTL_DAYS
from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.security.authorization import (
    AuthorizationDecision,
    AuthorizationEvaluator,
)
from app.core.security.policy_loader import (
    AuthorizationPolicy,
    GrantedPermission,
    PolicyLoader,
)
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class AuthorizationService:
    """Evaluates tool invocations against project authorization policies."""

    def __init__(self, project_id: int | None):
        self.project_id = project_id
        self._evaluator = AuthorizationEvaluator(project_id)
        self._policies: list[AuthorizationPolicy] | None = None
        self._granted: list[GrantedPermission] | None = None

    async def _load(self) -> None:
        if self._policies is not None:
            return
        await self._evaluator._load()
        self._policies = self._evaluator.policies
        self._granted = self._evaluator.granted

    async def evaluate(
        self,
        tool_name: str,
        tool_input: Any,
    ) -> AuthorizationDecision:
        """Evaluate whether the tool invocation is authorized."""
        decision = await self._evaluator.evaluate(tool_name, tool_input)
        # Mirror evaluator state so callers using _load/_granted keep working.
        self._policies = self._evaluator.policies
        self._granted = self._evaluator.granted
        return decision

    async def request_authorization(
        self,
        thread_id: str,
        tool_name: str,
        tool_call_id: str,
        decision: AuthorizationDecision,
        project_id: int | None = None,
        run_id: str | None = None,
        parent_id: str | None = None,
        original_tool_name: str | None = None,
        original_tool_args: dict | None = None,
    ) -> None:
        """Trigger HITL authorization request."""
        if decision.policy is None:
            raise ValueError(i18n.get("hitl.authorization.missing_policy_error"))

        await HITLOrchestrator.request_authorization(
            thread_id=thread_id,
            action_description=i18n.get(
                f"hitl.authorization.action.{decision.action}",
                default=f"{decision.action} {decision.resource_path}",
                resource_path=decision.resource_path,
            ),
            resource_path=decision.resource_path,
            risk_level=decision.policy.risk_level,
            policy=decision.policy.to_dict(),
            project_id=project_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            parent_id=parent_id,
            original_tool_name=original_tool_name or tool_name,
            original_tool_args=original_tool_args,
            # 透传规范 action（"read"/"write"），供批准后 grant 落盘与钩子比对一致。
            action=decision.action,
        )

    async def grant_permission(
        self,
        resource_path: str,
        action: str,
        granted_by: str | None = None,
        ttl_days: int | None = DEFAULT_AUTHORIZATION_TTL_DAYS,
    ) -> bool:
        """Persist a user-granted permission to project.json.

        ``ttl_days=None`` 表示永久授权（allow always，expires_at=None）。
        """
        if not self.project_id:
            return False

        now = datetime.now(timezone.utc)
        permission = GrantedPermission(
            path=resource_path,
            action=action,
            approved_at=now,
            expires_at=None if ttl_days is None else now + timedelta(days=ttl_days),
            granted_by=granted_by,
        )
        return await PolicyLoader.save_granted_permission(self.project_id, permission)

    async def is_granted(
        self,
        resource_path: str,
        action: str,
        now: datetime | None = None,
    ) -> bool:
        """持久化授权是否命中（path+action 匹配且未过期）。

        宏的"总是允许"（grant_mode=always → ``expires_at=None`` 永久 grant）与
        普通 TTL grant 均在此命中；调用方（如 run_macro 门控）据此短路后续
        确认。project_id 缺失时返回 False（无授权域可查）。
        """
        if not self.project_id:
            return False
        perms = await PolicyLoader.load_granted_permissions(self.project_id)
        if now is None:
            now = datetime.now(timezone.utc)
        for perm in perms:
            if perm.path != resource_path or perm.action != action:
                continue
            if perm.is_expired(now):
                continue
            return True
        return False


# Backward-compatible re-export of the decision model.
# New code should import from app.core.security.authorization.
__all__ = ["AuthorizationService", "AuthorizationDecision"]
