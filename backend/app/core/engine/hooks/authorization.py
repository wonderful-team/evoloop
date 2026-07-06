"""
Authorization gate hook.

Replaces the hard-coded sensitive_file_protection_gate with a project-configurable
policy engine that escalates to HITL approval instead of blindly blocking.
"""

import logging
import os
from datetime import datetime, timezone

from app.core.config import settings
from app.core.engine.hooks.core import HookContext, HookEvent, HookResult, hook_system
from app.core.engine.state.sub_schemas import PendingApproval
from app.core.hitl.authorization import AuthorizationDecision, AuthorizationService
from app.core.hitl.policies import AuthorizationPolicy
from app.core.project.utils import get_project_path

logger = logging.getLogger(__name__)


def _path_contains_evoloop(tool_input) -> bool:
    """Check if any path argument touches the project metadata directory."""
    if tool_input is None:
        return False
    paths = []
    if tool_input.path:
        paths.append(tool_input.path)
    if tool_input.args:
        for key in ("AbsolutePath", "TargetFile", "SearchPath", "TargetDirectory", "DirectoryPath"):
            val = tool_input.args.get(key)
            if val and isinstance(val, str):
                paths.append(val)
    return any(".evoloop" in p.lower() for p in paths)


def _extract_path_from_input(tool_name: str, tool_input) -> tuple[str, str] | None:
    if tool_input is None:
        return None
    path = getattr(tool_input, "path", None)
    if path:
        action = "write" if "write" in tool_name or "replace" in tool_name else "read"
        return str(path), action
    if tool_input.args:
        for key in ("TargetFile", "AbsolutePath", "SearchPath", "DirectoryPath", "TargetDirectory", "path"):
            val = tool_input.args.get(key)
            if val and isinstance(val, str):
                action = "write" if "write" in tool_name or "replace" in tool_name else "read"
                return val, action
    return None


def _is_path_safe(path_str: str, project_path: str | None) -> bool:
    try:
        resolved = os.path.realpath(os.path.expanduser(path_str))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
        resolved = os.path.abspath(os.path.expanduser(path_str))

    # Boundary 1: Active Project Workspace Root
    if project_path:
        try:
            resolved_proj = os.path.realpath(os.path.expanduser(project_path))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            resolved_proj = os.path.abspath(os.path.expanduser(project_path))
        if resolved == resolved_proj or resolved.startswith(resolved_proj + os.sep):
            return True

    # Boundary 2: App Data Directory (~/.evoloop)
    try:
        app_data = os.path.realpath(os.path.expanduser(settings.APP_DATA_DIR))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
        app_data = os.path.abspath(os.path.expanduser(settings.APP_DATA_DIR))
    if resolved == app_data or resolved.startswith(app_data + os.sep):
        return True

    # Boundary 3: ALLOWED_PATH_PREFIXES
    for prefix in getattr(settings, "ALLOWED_PATH_PREFIXES", []):
        try:
            resolved_prefix = os.path.realpath(os.path.expanduser(prefix))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            resolved_prefix = os.path.abspath(os.path.expanduser(prefix))
        if resolved == resolved_prefix or resolved.startswith(resolved_prefix + os.sep):
            return True

    return False


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher=".*", priority=1)
async def authorization_gate(context: HookContext) -> HookResult:
    """
    Project-level authorization gate.

    Runs before every tool use with the highest priority. If the tool touches a
    sensitive resource defined in the project's .evoloop/project.json, and the user
    has not already granted permission, it raises a HITL authorization request.
    """
    if not context.project_id:
        # Global mode: no project-specific authorization policies
        return HookResult(success=True)

    # Project metadata is always protected (no HITL escalation).
    if _path_contains_evoloop(context.tool_input):
        return HookResult(
            block=True,
            message="[SECURITY VIOLATION] Access to project metadata (.evoloop) is prohibited.",
        )

    auth_service = AuthorizationService(context.project_id)
    decision = await auth_service.evaluate(
        tool_name=context.tool_name or "",
        tool_input=context.tool_input,
    )

    # Extra CowAgent-inspired Safety Boundary check for file tools
    extracted = _extract_path_from_input(context.tool_name or "", context.tool_input)
    if extracted is not None:
        resource_path, action = extracted
        try:
            project_path = await get_project_path(context.project_id)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError):
            project_path = None

        if not _is_path_safe(resource_path, project_path):
            # Check if this permission was already granted previously
            is_already_granted = False
            now = datetime.now(timezone.utc)
            # Make sure we load granted permissions
            await auth_service._load()
            for grant in (auth_service._granted or []):
                # Check match
                # Try relative paths as well
                check_paths = [resource_path]
                if project_path and os.path.isabs(resource_path):
                    try:
                        rel = os.path.relpath(resource_path, project_path)
                        if not rel.startswith(".."):
                            check_paths.append(rel)
                    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                        logger.debug("Suppressed error: %s", e, exc_info=True)
                if grant.action == action and grant.path in check_paths:
                    if not grant.is_expired(now):
                        is_already_granted = True
                        break

            if not is_already_granted:
                # Trigger HITL instead of hard blocking
                policy = AuthorizationPolicy(
                    resource_type="file",
                    action=action,
                    patterns=[resource_path],
                    requires_approval=True,
                    risk_level="high",
                    description=f"Sensitive file access outside allowed workspace boundaries: {resource_path}"
                )
                decision = AuthorizationDecision(
                    approved=False,
                    requires_hitl=True,
                    reason=f"Access to {resource_path} requires user approval (outside workspace/allowed boundaries)",
                    policy=policy,
                    resource_path=resource_path,
                    action=action,
                )

    if decision.approved and not decision.requires_hitl:
        return HookResult(success=True)

    if decision.requires_hitl and decision.policy is not None:
        # Record pending approval in blackboard so the resume handler can persist it
        if context.state is not None:
            tool_args = {}
            if context.tool_input is not None:
                tool_args = context.tool_input.args or {}
                for field in ("command", "path", "content", "query"):
                    val = getattr(context.tool_input, field)
                    if val is not None:
                        tool_args[field] = val
            context.state.metadata.pending_approvals.append(
                PendingApproval(
                    tool_name=context.tool_name or "",
                    tool_call_id=context.tool_use_id or "",
                    resource_path=decision.resource_path,
                    action=decision.action,
                    risk_level=decision.policy.risk_level,
                    requested_at=datetime.now(timezone.utc).isoformat(),
                    tool_args=tool_args,
                )
            )

        tool_args = {}
        if context.tool_input is not None:
            tool_args = context.tool_input.args or {}
            for field in ("command", "path", "content", "query"):
                val = getattr(context.tool_input, field)
                if val is not None:
                    tool_args[field] = val

        await auth_service.request_authorization(
            thread_id=context.thread_id,
            tool_name=context.tool_name or "",
            tool_call_id=context.tool_use_id or "",
            decision=decision,
            project_id=context.project_id,
            run_id=context.run_id,
            original_tool_name=context.tool_name or "",
            original_tool_args=tool_args,
        )
        # request_authorization raises AgentHumanInterruptException; the blocked tool
        # itself is never executed. On approval the resume handler re-invokes the tool.
        return HookResult(success=True)

    # Block without HITL (policy match but approval not available / error path)
    return HookResult(
        block=True,
        message=f"[AUTHORIZATION DENIED] {decision.reason}",
    )
