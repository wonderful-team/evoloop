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


def tool_permission_rule(tool_name: str) -> str | None:
    """读取工具级权限规则（config 驱动 allow/ask/deny）。"""
    from app.core.config import settings

    rule = (settings.TOOL_PERMISSIONS or {}).get(tool_name)
    if rule is None:
        return None
    return str(rule).strip().lower()


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

    # File tools（2026-09 收敛：read/write/edit/list_dir/move_file/delete_file
    # 六件套并入 file facade，按 action 分流读写语义。旧引擎时代工具名
    # （view_file/write_to_file/replace_file_content 及收敛前的 read/write/edit）
    # 不做映射——authorization gate 只处理当前 registry 的活工具调用，
    # 历史消息不重放（messages 库实证：旧引擎名零留存）。
    if tool_name == "file":
        action = None
        if tool_input.args:
            action = tool_input.args.get("action")
        path = tool_input.path or (
            tool_input.args.get("path") if tool_input.args else None
        )
        if path:
            resource_action = "read" if action in (None, "read", "list") else "write"
            return str(path), resource_action
        return None

    if tool_name == "grep":
        path = tool_input.args.get("SearchPath") if tool_input.args else None
        if path:
            return str(path), "read"
        return None

    # Command tool
    if tool_name == "bash":
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

    async def _evaluate_tool_permission(
        self, tool_name: str
    ) -> AuthorizationDecision | None:
        """工具级权限（OpenCode Permission ruleset 等价物，config 驱动 allow/ask/deny）。

        返回 None 表示该工具不在 ``TOOL_PERMISSIONS`` 内（走资源级授权）。
        "ask" 时已批准（grant 未过期）自动放行，对齐 OpenCode approved rules。
        """
        rule = tool_permission_rule(tool_name)
        if rule is None:
            return None
        if rule == "deny":
            return AuthorizationDecision(
                approved=False,
                requires_hitl=False,
                reason=i18n.get(
                    "hitl.authorization.tool_denied",
                    default=f"Tool {tool_name} is denied by permission policy.",
                    tool=tool_name,
                ),
                resource_path=tool_name,
                action="invoke",
            )
        if rule == "ask":
            now = datetime.now(timezone.utc)
            for grant in self._granted or []:
                if (
                    grant.path == tool_name
                    and grant.action == "invoke"
                    and not grant.is_expired(now)
                ):
                    return AuthorizationDecision(
                        approved=True,
                        requires_hitl=False,
                        reason=i18n.get("hitl.authorization.previously_authorized"),
                        resource_path=tool_name,
                        action="invoke",
                    )
            policy = AuthorizationPolicy(
                resource_type="tool",
                action=tool_name,
                patterns=[tool_name],
                requires_approval=True,
                risk_level="medium",
                description=i18n.get(
                    "hitl.authorization.tool_ask_description",
                    default=f"Tool {tool_name} requires approval.",
                    tool=tool_name,
                ),
            )
            return AuthorizationDecision(
                approved=False,
                requires_hitl=True,
                reason=i18n.get(
                    "hitl.authorization.tool_requires_approval",
                    default=f"Tool {tool_name} requires approval.",
                    tool=tool_name,
                ),
                policy=policy,
                resource_path=tool_name,
                action="invoke",
            )
        # "allow"
        return AuthorizationDecision(
            approved=True,
            requires_hitl=False,
            reason=i18n.get(
                "hitl.authorization.tool_allowed",
                default=f"Tool {tool_name} is allowed.",
                tool=tool_name,
            ),
            resource_path=tool_name,
            action="invoke",
        )

    async def evaluate(
        self,
        tool_name: str,
        tool_input: Any,
    ) -> AuthorizationDecision:
        """Evaluate whether the tool invocation is authorized."""
        await self._load()

        # ① 工具级权限（config 驱动 allow/ask/deny）——命中即返回，不落资源级。
        tool_decision = await self._evaluate_tool_permission(tool_name)
        if tool_decision is not None:
            return tool_decision

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
