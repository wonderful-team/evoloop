"""
Unit tests for app.core.hitl authorization framework.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from app.core.engine.hooks.schemas import HookContext, ToolInput
from app.core.hitl import (
    AuthorizationPolicy,
    AuthorizationService,
    PolicyLoader,
)
from app.core.hitl.policies import DEFAULT_SENSITIVE_PATTERNS, GrantedPermission


class TestPolicyMatching:
    def test_match_env_file(self):
        assert PolicyLoader.match_path(".env", ["*.env"]) is True
        assert PolicyLoader.match_path("./.env", ["*.env"]) is True
        assert PolicyLoader.match_path("config/.env", ["*.env"]) is True
        assert PolicyLoader.match_path(".env.local", [".env.*"]) is True

    def test_no_match(self):
        assert PolicyLoader.match_path("README.md", ["*.env"]) is False

    def test_match_command(self):
        assert PolicyLoader.match_path("sudo rm -rf /", ["sudo *"]) is True
        assert PolicyLoader.match_path("rm -rf /", ["rm -rf /"]) is True


class TestAuthorizationPolicy:
    def test_to_dict_roundtrip(self):
        policy = AuthorizationPolicy(
            resource_type="file",
            action="read",
            patterns=["*.env"],
            requires_approval=True,
            risk_level="high",
            description="test",
        )
        assert AuthorizationPolicy.from_dict(policy.to_dict()) == policy


class TestGrantedPermission:
    def test_is_expired(self):
        now = datetime.now(timezone.utc)
        expired = GrantedPermission(
            path=".env",
            action="read",
            approved_at=now - timedelta(days=10),
            expires_at=now - timedelta(days=1),
        )
        assert expired.is_expired(now) is True

        valid = GrantedPermission(
            path=".env",
            action="read",
            approved_at=now,
            expires_at=now + timedelta(days=7),
        )
        assert valid.is_expired(now) is False


class TestAuthorizationService:
    @pytest.fixture
    def temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            evoloop_dir = os.path.join(tmpdir, ".evoloop")
            os.makedirs(evoloop_dir)
            project_json = os.path.join(evoloop_dir, "project.json")
            with open(project_json, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "project_id": 99999,
                        "sensitive_patterns": DEFAULT_SENSITIVE_PATTERNS,
                        "authorized_paths": [],
                    },
                    f,
                )
            yield tmpdir

    def test_no_project_id_allows_all(self):
        svc = AuthorizationService(None)
        decision = asyncio.run(
            svc.evaluate("read_file", ToolInput(path=".env"))
        )
        assert decision.approved is True
        assert decision.requires_hitl is False

    def test_sensitive_file_requires_hitl(self, temp_project, monkeypatch):
        async def _mock_get_project_path(pid):
            return temp_project if pid == 99999 else None

        monkeypatch.setattr(
            "app.core.hitl.policies.get_project_path",
            _mock_get_project_path,
        )
        svc = AuthorizationService(99999)
        decision = asyncio.run(
            svc.evaluate("read_file", ToolInput(path=".env"))
        )
        assert decision.approved is False
        assert decision.requires_hitl is True
        assert decision.policy is not None

    def test_non_sensitive_file_allowed(self, temp_project, monkeypatch):
        async def _mock_get_project_path(pid):
            return temp_project if pid == 99999 else None

        monkeypatch.setattr(
            "app.core.hitl.policies.get_project_path",
            _mock_get_project_path,
        )
        svc = AuthorizationService(99999)
        decision = asyncio.run(
            svc.evaluate("read_file", ToolInput(path="README.md"))
        )
        assert decision.approved is True
        assert decision.requires_hitl is False

    def test_granted_permission_allows_access(self, temp_project, monkeypatch):
        async def _mock_get_project_path(pid):
            return temp_project if pid == 99999 else None

        monkeypatch.setattr(
            "app.core.hitl.policies.get_project_path",
            _mock_get_project_path,
        )
        svc = AuthorizationService(99999)
        asyncio.run(svc.grant_permission(".env", "read", ttl_days=7))

        decision = asyncio.run(
            svc.evaluate("read_file", ToolInput(path=".env"))
        )
        assert decision.approved is True
        assert decision.requires_hitl is False
        assert "Previously authorized" in decision.reason


class TestAuthorizationHook:
    def test_blocks_evoloop_metadata(self):
        from app.core.engine.hooks.authorization import authorization_gate

        ctx = HookContext(
            thread_id="test-thread",
            project_id=57,
            tool_name="read_file",
            tool_input=ToolInput(path=".evoloop/project.json"),
        )
        result = asyncio.run(authorization_gate(ctx))
        assert result.block is True
        assert ".evoloop" in result.message

    def test_allows_non_project_mode(self):
        from app.core.engine.hooks.authorization import authorization_gate

        ctx = HookContext(
            thread_id="test-thread",
            project_id=None,
            tool_name="read_file",
            tool_input=ToolInput(path=".env"),
        )
        result = asyncio.run(authorization_gate(ctx))
        assert result.block is False
        assert result.success is True
