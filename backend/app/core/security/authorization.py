"""Pure authorization policy evaluation.

This module decides whether a tool invocation is allowed, needs approval, or
should be blocked based on project-level policies and previously granted
permissions. It does **not** raise HITL interrupts or orchestrate human
interactions — that remains the responsibility of ``app.core.hitl``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.project.utils import get_project_path
from app.core.security.policy_loader import (
    AuthorizationPolicy,
    GrantedPermission,
    PolicyLoader,
)
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


@dataclass
class AuthorizationDecision:
    approved: bool
    requires_hitl: bool
    reason: str
    policy: AuthorizationPolicy | None = None
    resource_path: str = ""
    action: str = ""


def _extract_resource(tool_name: str, tool_input: Any) -> tuple[str, str] | None:
    """
    Extract (resource_path, action) from a tool invocation.

    Returns None if the tool is outside the scope of project-level authorization.
    """
    if tool_input is None:
        return None

    # File tools
    if tool_name in ("read_file", "view_file"):
        path = tool_input.path or (
            tool_input.args.get("path") if tool_input.args else None
        )
        if path:
            return str(path), "read"
        return None

    if tool_name in (
        "replace_file_content",
        "multi_replace_file_content",
        "write_to_file",
    ):
        path = tool_input.path or (
            tool_input.args.get("path") if tool_input.args else None
        )
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
        command = tool_input.command or (
            tool_input.args.get("command") if tool_input.args else None
        )
        if command:
            return str(command), "execute"
        return None

    return None


class AuthorizationEvaluator:
    """Evaluates tool invocations against project authorization policies."""

    def __init__(self, project_id: int | None):
        self.project_id = project_id
        self._policies: list[AuthorizationPolicy] | None = None
        self._granted: list[GrantedPermission] | None = None

    @property
    def policies(self) -> list[AuthorizationPolicy] | None:
        return self._policies

    @property
    def granted(self) -> list[GrantedPermission] | None:
        return self._granted

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
                reason=i18n.get("hitl.authorization.tool_not_subject_to_authorization"),
            )

        resource_path, action = extracted

        # Normalize absolute paths to project-relative paths for matching and persistence.
        if action != "execute" and self.project_id:
            try:
                project_path = await get_project_path(self.project_id)
            except Exception:
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
                reason=i18n.get("hitl.authorization.no_matching_policy"),
            )

        if not matched_policy.requires_approval:
            return AuthorizationDecision(
                approved=True,
                requires_hitl=False,
                reason=i18n.get("hitl.authorization.policy_no_approval_required"),
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
                    reason=i18n.get("hitl.authorization.previously_authorized"),
                    policy=matched_policy,
                    resource_path=resource_path,
                    action=action,
                )

        # Approval required
        return AuthorizationDecision(
            approved=False,
            requires_hitl=True,
            reason=i18n.get(
                "hitl.authorization.access_requires_approval",
                resource_path=resource_path,
            ),
            policy=matched_policy,
            resource_path=resource_path,
            action=action,
        )

    def get_granted(self) -> list[GrantedPermission] | None:
        """Return loaded granted permissions (for callers that need to check expiry)."""
        return self._granted
