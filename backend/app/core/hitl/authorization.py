"""
Authorization framework for project-level resource access control.

The authorization service evaluates whether a tool invocation is allowed, needs
user approval, or should be blocked. When approval is required it delegates to
HITLOrchestrator.request_authorization() which raises AgentHumanInterruptException.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.hitl.orchestrator import HITLOrchestrator
from app.core.hitl.policies import (
    AuthorizationPolicy,
    GrantedPermission,
    PolicyLoader,
)
from app.core.project.utils import get_project_path

logger = logging.getLogger(__name__)


# ============ Decision Model ============


@dataclass
class AuthorizationDecision:
    approved: bool
    requires_hitl: bool
    reason: str
    policy: AuthorizationPolicy | None = None
    resource_path: str = ""
    action: str = ""


# ============ Resource Extraction ============


def _extract_resource(tool_name: str, tool_input: Any) -> tuple[str, str] | None:
    """
    Extract (resource_path, action) from a tool invocation.

    Returns None if the tool is outside the scope of project-level authorization.
    """
    if tool_input is None:
        return None

    # File tools
    if tool_name in ("read_file", "view_file"):
        path = tool_input.path or (tool_input.args.get("path") if tool_input.args else None)
        if path:
            return str(path), "read"
        return None

    if tool_name in ("replace_file_content", "multi_replace_file_content", "write_to_file"):
        path = tool_input.path or (tool_input.args.get("path") if tool_input.args else None)
        if path:
            return str(path), "write"
        return None

    if tool_name == "grep_search":
        path = tool_input.args.get("SearchPath") if tool_input.args else None
        if path:
            return str(path), "read"
        return None

    # Command tool
    if tool_name == "execute_command":
        command = tool_input.command or (tool_input.args.get("command") if tool_input.args else None)
        if command:
            return str(command), "execute"
        return None

    return None


# ============ Service ============


class AuthorizationService:
    """Evaluates tool invocations against project authorization policies."""

    def __init__(self, project_id: int | None):
        self.project_id = project_id
        self._policies: list[AuthorizationPolicy] | None = None
        self._granted: list[GrantedPermission] | None = None

    async def _load(self) -> None:
        if self._policies is not None:
            return
        if self.project_id:
            self._policies = await PolicyLoader.load_policies(self.project_id)
            self._granted = await PolicyLoader.load_granted_permissions(self.project_id)
        else:
            self._policies = []
            self._granted = []

    async def evaluate(
        self,
        tool_name: str,
        tool_input: Any,
    ) -> AuthorizationDecision:
        """Evaluate whether the tool invocation is authorized."""
        await self._load()

        extracted = _extract_resource(tool_name, tool_input)
        if extracted is None:
            # Not a resource we authorize
            return AuthorizationDecision(
                approved=True,
                requires_hitl=False,
                reason="Tool not subject to project authorization",
            )

        resource_path, action = extracted

        # Normalize absolute paths to project-relative paths for matching and persistence.
        if action != "execute" and self.project_id:
            try:
                project_path = await get_project_path(self.project_id)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
                project_path = None
            if project_path and os.path.isabs(resource_path):
                rel_path = os.path.relpath(resource_path, project_path)
                if not rel_path.startswith(".."):
                    resource_path = rel_path

        # Find matching policy
        matched_policy: AuthorizationPolicy | None = None
        for policy in self._policies:
            if policy.action != action and policy.action != "*":
                continue
            if PolicyLoader.match_path(resource_path, policy.patterns):
                matched_policy = policy
                break

        if matched_policy is None:
            return AuthorizationDecision(
                approved=True,
                requires_hitl=False,
                reason="No matching authorization policy",
            )

        if not matched_policy.requires_approval:
            return AuthorizationDecision(
                approved=True,
                requires_hitl=False,
                reason="Policy does not require approval",
                policy=matched_policy,
                resource_path=resource_path,
                action=action,
            )

        # Check existing grants
        now = datetime.now(timezone.utc)
        for grant in self._granted or []:
            if grant.path == resource_path and grant.action == action:
                if grant.is_expired(now):
                    continue
                return AuthorizationDecision(
                    approved=True,
                    requires_hitl=False,
                    reason="Previously authorized by user",
                    policy=matched_policy,
                    resource_path=resource_path,
                    action=action,
                )

        # Approval required
        return AuthorizationDecision(
            approved=False,
            requires_hitl=True,
            reason=f"Access to {resource_path} requires user approval",
            policy=matched_policy,
            resource_path=resource_path,
            action=action,
        )

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
            raise ValueError("Cannot request authorization without a matching policy")

        await HITLOrchestrator.request_authorization(
            thread_id=thread_id,
            action_description=f"{decision.action} {decision.resource_path}",
            resource_path=decision.resource_path,
            risk_level=decision.policy.risk_level,
            policy=decision.policy.to_dict(),
            project_id=project_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            parent_id=parent_id,
            original_tool_name=original_tool_name or tool_name,
            original_tool_args=original_tool_args,
        )

    async def grant_permission(
        self,
        resource_path: str,
        action: str,
        granted_by: str | None = None,
        ttl_days: int = 7,
    ) -> bool:
        """Persist a user-granted permission to project.json."""
        if not self.project_id:
            return False

        now = datetime.now(timezone.utc)
        permission = GrantedPermission(
            path=resource_path,
            action=action,
            approved_at=now,
            expires_at=now + timedelta(days=ttl_days),
            granted_by=granted_by,
        )
        return await PolicyLoader.save_granted_permission(self.project_id, permission)
