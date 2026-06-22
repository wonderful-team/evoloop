"""
Authorization gate hook.

Replaces the hard-coded sensitive_file_protection_gate with a project-configurable
policy engine that escalates to HITL approval instead of blindly blocking.
"""

import logging
from datetime import datetime, timezone

from app.core.engine.hooks.core import HookContext, HookEvent, HookResult, hook_system
from app.core.engine.state.sub_schemas import PendingApproval
from app.core.hitl.authorization import AuthorizationService

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
