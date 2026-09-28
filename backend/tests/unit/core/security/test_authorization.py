"""Unit tests for app.core.security.authorization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.engine.hooks.schemas import ToolInput
from app.core.security.authorization import (
    AuthorizationEvaluator,
    _extract_resource,
)
from app.core.security.policy_loader import AuthorizationPolicy, GrantedPermission


class TestExtractResource:
    def _ti(self, **kwargs):
        from app.core.engine.hooks.schemas import ToolInput
        return ToolInput.model_validate(kwargs)

    def test_extracts_read_file_path(self):
        assert _extract_resource("file", self._ti(args={"action": "read", "path": "/tmp/a"})) == (
            "/tmp/a",
            "read",
        )

    def test_extracts_write_file_path(self):
        assert _extract_resource("file", self._ti(args={"action": "write", "path": "/tmp/a"})) == (
            "/tmp/a",
            "write",
        )

    def test_legacy_engine_tool_names_not_authorized(self):
        """旧引擎时代工具名不在授权范围（gate 只处理当前 registry 活工具）。"""
        assert _extract_resource("write_to_file", self._ti(path="/tmp/a")) is None
        assert _extract_resource("replace_file_content", self._ti(path="/tmp/a")) is None

    def test_extracts_grep_search_path(self):
        assert _extract_resource("grep", self._ti(args={"SearchPath": "/tmp"})) == (
            "/tmp",
            "read",
        )

    def test_extracts_execute_command(self):
        assert _extract_resource("bash", self._ti(command="ls")) == ("ls", "execute")

    def test_returns_none_for_unrelated_tool(self):
        assert _extract_resource("list_macros", self._ti()) is None


@pytest.mark.asyncio
class TestAuthorizationEvaluator:
    async def test_no_policies_approves(self):
        with patch(
            "app.core.security.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[]),
        ):
            evaluator = AuthorizationEvaluator(project_id=120)
            decision = await evaluator.evaluate(
                "file", ToolInput(path=".env", args={"action": "read"})
            )
        assert decision.approved is True
        assert decision.requires_hitl is False

    async def test_matching_policy_without_approval_approves(self):
        policy = AuthorizationPolicy(
            resource_type="file",
            action="read",
            patterns=["public/*"],
            requires_approval=False,
        )
        with patch(
            "app.core.security.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[policy]),
        ):
            evaluator = AuthorizationEvaluator(project_id=120)
            decision = await evaluator.evaluate("file", ToolInput(path="public/info.txt"))
        assert decision.approved is True
        assert decision.requires_hitl is False

    async def test_matching_policy_requires_hitl(self):
        policy = AuthorizationPolicy(
            resource_type="file",
            action="read",
            patterns=["*.env"],
            requires_approval=True,
            risk_level="high",
        )
        with patch(
            "app.core.security.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[policy]),
        ), patch(
            "app.core.security.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=[]),
        ):
            evaluator = AuthorizationEvaluator(project_id=120)
            decision = await evaluator.evaluate("file", ToolInput(path="keys/.env"))
        assert decision.approved is False
        assert decision.requires_hitl is True
        assert decision.policy is policy

    async def test_existing_grant_approves(self):
        policy = AuthorizationPolicy(
            resource_type="file",
            action="read",
            patterns=["*.env"],
            requires_approval=True,
        )
        now = datetime.now(timezone.utc)
        grant = GrantedPermission(
            path="keys/.env",
            action="read",
            approved_at=now,
            expires_at=now + timedelta(days=7),
        )
        with patch(
            "app.core.security.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[policy]),
        ), patch(
            "app.core.security.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=[grant]),
        ):
            evaluator = AuthorizationEvaluator(project_id=120)
            decision = await evaluator.evaluate("file", ToolInput(path="keys/.env"))
        assert decision.approved is True
        assert decision.requires_hitl is False

    async def test_expired_grant_does_not_approve(self):
        policy = AuthorizationPolicy(
            resource_type="file",
            action="read",
            patterns=["*.env"],
            requires_approval=True,
        )
        now = datetime.now(timezone.utc)
        grant = GrantedPermission(
            path="keys/.env",
            action="read",
            approved_at=now - timedelta(days=14),
            expires_at=now - timedelta(days=7),
        )
        with patch(
            "app.core.security.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[policy]),
        ), patch(
            "app.core.security.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=[grant]),
        ):
            evaluator = AuthorizationEvaluator(project_id=120)
            decision = await evaluator.evaluate("file", ToolInput(path="keys/.env"))
        assert decision.approved is False
        assert decision.requires_hitl is True

    async def test_no_project_approves_everything(self):
        evaluator = AuthorizationEvaluator(project_id=None)
        decision = await evaluator.evaluate("file", ToolInput(path="/etc/passwd"))
        assert decision.approved is True

    async def test_evaluator_state_properties(self):
        policy = AuthorizationPolicy(resource_type="file", action="read", patterns=["*"])
        grant = GrantedPermission(
            path="x",
            action="read",
            approved_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        with patch(
            "app.core.security.authorization.PolicyLoader.load_policies",
            AsyncMock(return_value=[policy]),
        ), patch(
            "app.core.security.authorization.PolicyLoader.load_granted_permissions",
            AsyncMock(return_value=[grant]),
        ):
            evaluator = AuthorizationEvaluator(project_id=1)
            await evaluator.evaluate("file", ToolInput(path="x"))
        assert evaluator.policies == [policy]
        assert evaluator.granted == [grant]
        assert evaluator.get_granted() == [grant]
