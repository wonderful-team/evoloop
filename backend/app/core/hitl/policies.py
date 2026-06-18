"""
Authorization policy loader and persistence.

Policies and granted permissions are stored in the project's .evoloop/project.json.
"""

import fnmatch
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.project.utils import get_project_path

logger = logging.getLogger(__name__)

# Default lifetime of a granted permission.
DEFAULT_PERMISSION_TTL_DAYS = 7


# ============ Data Models ============


@dataclass
class AuthorizationPolicy:
    """A single project-level authorization policy."""

    resource_type: str  # e.g. "file", "command"
    action: str  # e.g. "read", "write", "execute"
    patterns: list[str]  # glob patterns relative to project root
    requires_approval: bool = True
    risk_level: str = "medium"  # low, medium, high, critical
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "resource_type": self.resource_type,
            "action": self.action,
            "patterns": self.patterns,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuthorizationPolicy":
        return cls(
            resource_type=data.get("resource_type", "file"),
            action=data.get("action", "read"),
            patterns=list(data.get("patterns", [])),
            requires_approval=data.get("requires_approval", True),
            risk_level=data.get("risk_level", "medium"),
            description=data.get("description", ""),
        )


@dataclass
class GrantedPermission:
    """A user-granted permission persisted in project.json."""

    path: str
    action: str
    approved_at: datetime
    expires_at: datetime
    granted_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "action": self.action,
            "approved_at": self.approved_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "granted_by": self.granted_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GrantedPermission":
        return cls(
            path=data["path"],
            action=data.get("action", "read"),
            approved_at=datetime.fromisoformat(data["approved_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            granted_by=data.get("granted_by"),
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return now >= self.expires_at


# ============ Defaults ============


DEFAULT_SENSITIVE_PATTERNS: list[dict] = [
    {
        "resource_type": "file",
        "action": "read",
        "patterns": ["*.env", ".env.*"],
        "requires_approval": True,
        "risk_level": "high",
        "description": "Environment files may contain secrets.",
    },
    {
        "resource_type": "file",
        "action": "write",
        "patterns": ["*.env", ".env.*"],
        "requires_approval": True,
        "risk_level": "critical",
        "description": "Writing environment files is highly sensitive.",
    },
    {
        "resource_type": "file",
        "action": "read",
        "patterns": ["deploy/profiles/*"],
        "requires_approval": True,
        "risk_level": "medium",
        "description": "Customer deployment profiles contain environment-specific configuration.",
    },
    {
        "resource_type": "file",
        "action": "write",
        "patterns": ["deploy/profiles/*"],
        "requires_approval": True,
        "risk_level": "high",
        "description": "Writing customer deployment profiles is sensitive.",
    },
    {
        "resource_type": "file",
        "action": "read",
        "patterns": [".aws/credentials", ".aws/config"],
        "requires_approval": True,
        "risk_level": "high",
        "description": "AWS credential files contain cloud access keys.",
    },
    {
        "resource_type": "file",
        "action": "read",
        "patterns": ["config/secrets.*", "config/*.secret", "secrets/*"],
        "requires_approval": True,
        "risk_level": "high",
        "description": "Secret configuration files.",
    },
    {
        "resource_type": "file",
        "action": "read",
        "patterns": [".ssh/*", ".ssh/id_*"],
        "requires_approval": True,
        "risk_level": "critical",
        "description": "SSH private keys grant remote server access.",
    },
    {
        "resource_type": "command",
        "action": "execute",
        "patterns": ["sudo *", "su *", "pkexec *"],
        "requires_approval": True,
        "risk_level": "critical",
        "description": "Privilege escalation commands.",
    },
    {
        "resource_type": "command",
        "action": "execute",
        "patterns": ["rm -rf /", "rm -rf /*", "mkfs.*", ":(){ :|: & };:"],
        "requires_approval": True,
        "risk_level": "critical",
        "description": "Destructive or dangerous commands.",
    },
]


# ============ Loader ============


class PolicyLoader:
    """Loads authorization policies and granted permissions from project.json."""

    @staticmethod
    async def _project_json_path(project_id: int) -> str | None:
        project_path = await get_project_path(project_id)
        if not project_path:
            return None
        return os.path.join(project_path, ".evoloop", "project.json")

    @staticmethod
    async def _read_meta(project_id: int) -> dict:
        meta_path = await PolicyLoader._project_json_path(project_id)
        if not meta_path or not os.path.exists(meta_path):
            return {}
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[PolicyLoader] Failed to read {meta_path}: {e}")
            return {}

    @staticmethod
    async def _write_meta(project_id: int, meta: dict) -> bool:
        meta_path = await PolicyLoader._project_json_path(project_id)
        if not meta_path:
            return False
        try:
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.warning(f"[PolicyLoader] Failed to write {meta_path}: {e}")
            return False

    @staticmethod
    async def load_policies(project_id: int) -> list[AuthorizationPolicy]:
        """Load sensitive_patterns from project.json, falling back to defaults."""
        meta = await PolicyLoader._read_meta(project_id)
        raw_policies = meta.get("sensitive_patterns")
        if not raw_policies:
            raw_policies = DEFAULT_SENSITIVE_PATTERNS
        return [AuthorizationPolicy.from_dict(p) for p in raw_policies]

    @staticmethod
    async def load_granted_permissions(project_id: int) -> list[GrantedPermission]:
        """Load authorized_paths from project.json."""
        meta = await PolicyLoader._read_meta(project_id)
        raw = meta.get("authorized_paths", [])
        permissions = []
        for item in raw:
            try:
                permissions.append(GrantedPermission.from_dict(item))
            except Exception as e:
                logger.warning(f"[PolicyLoader] Invalid granted permission: {item} ({e})")
        return permissions

    @staticmethod
    async def save_granted_permission(
        project_id: int,
        permission: GrantedPermission,
    ) -> bool:
        """Append a granted permission to project.json."""
        meta = await PolicyLoader._read_meta(project_id)
        raw = meta.get("authorized_paths", [])

        # Remove any expired or duplicate entry for the same path+action
        cleaned = []
        for item in raw:
            try:
                if item.get("path") == permission.path and item.get("action") == permission.action:
                    continue
                cleaned.append(item)
            except Exception:
                continue

        cleaned.append(permission.to_dict())
        meta["authorized_paths"] = cleaned
        return await PolicyLoader._write_meta(project_id, meta)

    @staticmethod
    async def revoke_permission(project_id: int, path: str, action: str) -> bool:
        """Remove a granted permission from project.json."""
        meta = await PolicyLoader._read_meta(project_id)
        raw = meta.get("authorized_paths", [])
        meta["authorized_paths"] = [
            item for item in raw
            if not (item.get("path") == path and item.get("action") == action)
        ]
        return await PolicyLoader._write_meta(project_id, meta)

    @staticmethod
    async def ensure_defaults(project_id: int) -> bool:
        """If project.json has no sensitive_patterns, write the defaults."""
        meta = await PolicyLoader._read_meta(project_id)
        if "sensitive_patterns" not in meta:
            meta["sensitive_patterns"] = DEFAULT_SENSITIVE_PATTERNS
            meta.setdefault("authorized_paths", [])
            return await PolicyLoader._write_meta(project_id, meta)
        return True

    @staticmethod
    def match_path(path: str, patterns: list[str]) -> bool:
        """Match a path against a list of glob patterns.

        Supports project-relative, absolute, and workspace-relative paths by also
        matching path suffixes for patterns that contain a directory separator.
        """
        # Normalize leading ./ without stripping other dots (e.g. .env)
        clean_path = path[2:] if path.startswith("./") else path
        parts = clean_path.split("/")

        for pattern in patterns:
            clean_pattern = pattern[2:] if pattern.startswith("./") else pattern

            # Full / relative path match
            if fnmatch.fnmatch(clean_path, clean_pattern):
                return True

            # Basename-only patterns (e.g. *.env)
            if "/" not in clean_pattern:
                if fnmatch.fnmatch(os.path.basename(clean_path), clean_pattern):
                    return True
                continue

            # Directory-aware patterns: match any suffix starting at a path component.
            # This handles absolute paths and paths prefixed by the project folder.
            for start in range(len(parts)):
                suffix = "/".join(parts[start:])
                if fnmatch.fnmatch(suffix, clean_pattern):
                    return True

        return False
