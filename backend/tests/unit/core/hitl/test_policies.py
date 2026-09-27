"""Tests for the authorization policy loader and persistence layer."""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security.policy_loader import (
    DEFAULT_SENSITIVE_PATTERNS,
    AuthorizationPolicy,
    GrantedPermission,
    PolicyLoader,
)

# ============ Models ============


def test_policy_to_dict_from_dict_roundtrip():
    policy = AuthorizationPolicy(
        resource_type="file",
        action="write",
        patterns=["*.env"],
        requires_approval=True,
        risk_level="critical",
        description="Writing env files",
    )
    restored = AuthorizationPolicy.from_dict(policy.to_dict())
    assert restored == policy


def test_policy_from_dict_defaults():
    policy = AuthorizationPolicy.from_dict({"patterns": ["x/*"]})
    assert policy.resource_type == "file"
    assert policy.action == "read"
    assert policy.requires_approval is True
    assert policy.risk_level == "medium"


def test_granted_permission_to_dict_from_dict_roundtrip():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    permission = GrantedPermission(
        path="keys/.env",
        action="read",
        approved_at=now,
        expires_at=now + timedelta(days=7),
        granted_by="hitl-approval",
    )
    restored = GrantedPermission.from_dict(permission.to_dict())
    assert restored.path == "keys/.env"
    assert restored.action == "read"
    assert restored.granted_by == "hitl-approval"
    assert restored.approved_at == now


def test_granted_permission_is_expired():
    now = datetime.now(timezone.utc)
    past = GrantedPermission(
        path="x", action="read", approved_at=now, expires_at=now - timedelta(days=1)
    )
    future = GrantedPermission(
        path="x", action="read", approved_at=now, expires_at=now + timedelta(days=1)
    )
    assert past.is_expired() is True
    assert future.is_expired() is False


def test_granted_permission_is_expired_naive_expiry():
    """无时区 expires_at（旧数据）→ 用 naive now 比较，不抛异常。"""
    now = datetime.utcnow()
    permission = GrantedPermission(
        path="x", action="read", approved_at=now, expires_at=now - timedelta(hours=1)
    )
    assert permission.is_expired() is True


# ============ match_path ============


def test_match_path_basename_pattern():
    assert PolicyLoader.match_path("keys/.env", ["*.env"]) is True
    assert PolicyLoader.match_path("keys/app.log", ["*.env"]) is False


def test_match_path_relative_and_absolute():
    assert PolicyLoader.match_path("config/secrets.json", ["config/*.json"]) is True
    assert (
        PolicyLoader.match_path("/proj/config/secrets.json", ["config/*.json"]) is True
    )


def test_match_path_dot_slash_prefix_normalized():
    assert PolicyLoader.match_path("./keys/.env", ["*.env"]) is True
    assert PolicyLoader.match_path("keys/.env", ["./keys/*"]) is True


def test_match_path_suffix_matching_deep_absolute_paths():
    assert PolicyLoader.match_path("/a/b/c/.ssh/id_rsa", [".ssh/id_*"]) is True


def test_match_path_no_match():
    assert PolicyLoader.match_path("keys/.env", ["other/*"]) is False
    assert PolicyLoader.match_path("plain.txt", ["config/*"]) is False


# ============ PolicyLoader persistence ============


@contextmanager
def _project_json_at(tmp_path):
    """Patch ``_project_json_path`` to a tmp location and yield the file path."""
    project_json = tmp_path / ".evoloop" / "project.json"
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        yield project_json


@pytest.mark.asyncio
async def test_project_json_path_none_project():
    with patch("app.core.security.policy_loader.get_project_path", AsyncMock(return_value=None)):
        assert await PolicyLoader._project_json_path(120) is None


@pytest.mark.asyncio
async def test_project_json_path_built():
    with patch(
        "app.core.security.policy_loader.get_project_path",
        AsyncMock(return_value="/proj/evoloop"),
    ):
        path = await PolicyLoader._project_json_path(120)
        assert path == "/proj/evoloop/.evoloop/project.json"


@pytest.mark.asyncio
async def test_read_meta_missing_file_returns_empty(tmp_path):
    with _project_json_at(tmp_path):
        assert await PolicyLoader._read_meta(120) == {}


@pytest.mark.asyncio
async def test_read_meta_corrupt_json_returns_empty(tmp_path):
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text("{not-json", encoding="utf-8")
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        assert await PolicyLoader._read_meta(120) == {}


@pytest.mark.asyncio
async def test_write_meta_without_path_returns_false():
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=None),
    ):
        assert await PolicyLoader._write_meta(120, {"a": 1}) is False


@pytest.mark.asyncio
async def test_write_meta_persists(tmp_path):
    with _project_json_at(tmp_path) as project_json:
        assert await PolicyLoader._write_meta(120, {"a": 1}) is True
        assert json.loads(project_json.read_text(encoding="utf-8")) == {"a": 1}


@pytest.mark.asyncio
async def test_load_policies_defaults_when_absent(tmp_path):
    with _project_json_at(tmp_path):
        policies = await PolicyLoader.load_policies(120)
    assert len(policies) == len(DEFAULT_SENSITIVE_PATTERNS)
    assert policies[0].requires_approval is True


@pytest.mark.asyncio
async def test_load_policies_from_project_json(tmp_path):
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text(
        json.dumps(
            {
                "sensitive_patterns": [
                    {
                        "resource_type": "file",
                        "action": "read",
                        "patterns": ["custom/*"],
                        "requires_approval": False,
                        "risk_level": "low",
                        "description": "custom",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        policies = await PolicyLoader.load_policies(120)
    assert len(policies) == 1
    assert policies[0].patterns == ["custom/*"]
    assert policies[0].requires_approval is False


@pytest.mark.asyncio
async def test_load_granted_permissions_skips_invalid(tmp_path):
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text(
        json.dumps(
            {
                "authorized_paths": [
                    {
                        "path": "ok/.env",
                        "action": "read",
                        "approved_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": "2027-01-01T00:00:00+00:00",
                    },
                    {"path": "broken"},  # 缺 approved_at/expires_at → 跳过
                ]
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        permissions = await PolicyLoader.load_granted_permissions(120)
    assert len(permissions) == 1
    assert permissions[0].path == "ok/.env"


@pytest.mark.asyncio
async def test_save_granted_permission_dedup_and_append(tmp_path):
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text(
        json.dumps(
            {
                "authorized_paths": [
                    {
                        "path": "same/.env",
                        "action": "read",
                        "approved_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": "2027-01-01T00:00:00+00:00",
                    },
                    {
                        "path": "keep/.env",
                        "action": "read",
                        "approved_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": "2027-01-01T00:00:00+00:00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    now = datetime.now(timezone.utc)
    permission = GrantedPermission(
        path="same/.env",
        action="read",
        approved_at=now,
        expires_at=now + timedelta(days=7),
    )
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        assert await PolicyLoader.save_granted_permission(120, permission) is True

    saved = json.loads(project_json.read_text(encoding="utf-8"))["authorized_paths"]
    paths = [item["path"] for item in saved]
    # 同 path+action 旧条目被去重，仅保留新授权 + 无关条目
    assert paths == ["keep/.env", "same/.env"]


@pytest.mark.asyncio
async def test_revoke_permission_removes_matching(tmp_path):
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text(
        json.dumps(
            {
                "authorized_paths": [
                    {
                        "path": "a/.env",
                        "action": "read",
                        "approved_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": "2027-01-01T00:00:00+00:00",
                    },
                    {
                        "path": "a/.env",
                        "action": "write",
                        "approved_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": "2027-01-01T00:00:00+00:00",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        assert await PolicyLoader.revoke_permission(120, "a/.env", "read") is True

    saved = json.loads(project_json.read_text(encoding="utf-8"))["authorized_paths"]
    assert [item["action"] for item in saved] == ["write"]


@pytest.mark.asyncio
async def test_write_meta_failure_returns_false(tmp_path):
    """写盘失败 → 返回 False 且不抛异常（仅记录 warning）。"""
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text("{}", encoding="utf-8")
    with (
        patch(
            "app.core.security.policy_loader.PolicyLoader._project_json_path",
            AsyncMock(return_value=str(project_json)),
        ),
        patch(
            "app.core.security.policy_loader.os.makedirs", side_effect=PermissionError("denied")
        ),
    ):
        assert await PolicyLoader._write_meta(120, {"a": 1}) is False


@pytest.mark.asyncio
async def test_save_granted_permission_skips_non_dict_items(tmp_path):
    """authorized_paths 含非 dict 脏数据 → 跳过不崩溃。"""
    project_json = tmp_path / ".evoloop" / "project.json"
    project_json.parent.mkdir(parents=True)
    project_json.write_text(
        json.dumps({"authorized_paths": ["junk", None]}),
        encoding="utf-8",
    )
    now = datetime.now(timezone.utc)
    permission = GrantedPermission(
        path="new/.env",
        action="read",
        approved_at=now,
        expires_at=now + timedelta(days=7),
    )
    with patch(
        "app.core.security.policy_loader.PolicyLoader._project_json_path",
        AsyncMock(return_value=str(project_json)),
    ):
        assert await PolicyLoader.save_granted_permission(120, permission) is True

    saved = json.loads(project_json.read_text(encoding="utf-8"))["authorized_paths"]
    assert saved == [permission.to_dict()]
