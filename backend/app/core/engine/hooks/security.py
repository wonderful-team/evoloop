"""
Security Hooks for EvoLoop.

Provides security gates for tool execution:
- Sudo command blocking
- Dangerous command detection
- Permission escalation prevention
"""

import logging
import re

from app.core.engine.hooks.core import HookContext, HookEvent, HookResult, hook_system
from app.core.engine.hooks.schemas import ToolInput
from app.core.security.secrets import censor_tool_result, inject_secrets_into_tool_input

logger = logging.getLogger(__name__)


# Patterns that indicate commands requiring elevated privileges
_ELEVATED_PRIVILEGE_PATTERNS = [
    # sudo and variants
    (r"^\s*sudo\s+", "sudo", "管理员权限(sudo)"),
    # su command
    (r"^\s*su\s+(-|\w+)", "su", "用户切换(su)"),
    # pkexec
    (r"^\s*pkexec\s+", "pkexec", "权限提升(pkexec)"),
]

# Additional dangerous patterns to block
_DANGEROUS_PATTERNS = [
    # System modification commands that typically require root
    (r"^\s*passwd\s*\w*", "passwd", "密码修改"),
]


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher="^execute_command$", priority=5)
async def elevated_privilege_gate(context: HookContext) -> HookResult:
    """
    Block commands requiring elevated privileges (sudo, su, pkexec).

    This prevents the Agent from getting stuck waiting for password input,
    which would cause a timeout without clear error indication.

    Priority 5 (lower than default 100) ensures this runs early in the hook chain.
    """
    command = context.tool_input.command if context.tool_input else ""
    if not command:
        return HookResult(success=True)

    # Check for elevated privilege patterns
    for pattern, cmd_type, description in _ELEVATED_PRIVILEGE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            logger.warning(
                f"[SecurityHook] Blocked {cmd_type} command: {command[:100]}"
            )
            return HookResult(
                success=False,
                block=True,
                message=(
                    f"[BLOCKED] 命令执行被阻止：需要{description}\n\n"
                    f"命令：`{command[:200]}{'...' if len(command) > 200 else ''}`\n\n"
                    f"当前执行环境不支持交互式密码输入，此类命令会导致超时且无明确错误提示。\n\n"
                    f"**建议操作**：\n"
                    f"1. 寻找无需{description}的替代方案\n"
                    f"2. 使用 `ask_human` 工具请求用户协助执行\n"
                    f"3. 如需长期使用，请配置免密 sudo 或使用容器环境"
                ),
            )

    return HookResult(success=True)


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher="^execute_command$", priority=6)
async def dangerous_command_gate(context: HookContext) -> HookResult:
    """
    Block potentially dangerous system commands.

    These commands may cause system instability or security risks.
    Priority 6 runs after elevated_privilege_gate.
    """
    command = context.tool_input.command if context.tool_input else ""
    if not command:
        return HookResult(success=True)

    # Check for dangerous patterns
    for pattern, cmd_type, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            logger.warning(
                f"[SecurityHook] Blocked dangerous {cmd_type} command: {command[:100]}"
            )
            return HookResult(
                success=False,
                block=True,
                message=(
                    f"[SECURITY WARNING] 安全风险：{description}命令被阻止\n\n"
                    f"命令：`{command[:200]}{'...' if len(command) > 200 else ''}`\n\n"
                    f"此类命令可能影响系统安全或稳定性。\n\n"
                    f"**如需执行**：\n"
                    f"使用 `ask_human` 工具请求用户明确确认后手动执行"
                ),
            )

    return HookResult(success=True)


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher=".*", priority=3)
async def sensitive_file_placeholder_replacement_gate(
    context: HookContext,
) -> HookResult:
    """
    Scan tool inputs recursively for {{vault.id.key}} placeholders, decrypt values,
    and substitute them in-place. Record injected raw values in context.extra for post-execution censorship.
    """
    tool_input = context.tool_input
    if not tool_input:
        return HookResult(success=True)

    try:
        # Substitute placeholders across ALL tool input fields (declared + dynamic
        # extra fields). The 5 legacy fields (command/path/content/query/args) only
        # cover a subset of tools; run_macro's `params`, browser_control's action
        # fields etc. live in dynamic extra fields and previously bypassed vault
        # injection, causing {{vault.*}} placeholders to reach the target literally.
        original_input = tool_input.model_dump()
        replaced, injected_secrets = await inject_secrets_into_tool_input(
            original_input, project_id=context.project_id
        )
        if replaced != original_input:
            context.tool_input = ToolInput.model_validate(replaced)
    except ValueError as e:
        logger.exception(f"[SecureVault] Substitution failed: {e}")
        return HookResult(success=False, block=True, message=f"[SECURITY ERROR] {e}")

    # Save injected secrets in context.extra for post-execution sanitization
    if injected_secrets:
        context.extra["injected_secrets"] = list(injected_secrets)
        from app.core.context.manager import ContextManager

        try:
            ctx = ContextManager.current()
            if ctx.injected_secrets is None:
                ctx.injected_secrets = set()
            ctx.injected_secrets.update(injected_secrets)
        except Exception as e:
            logger.warning(
                f"Failed to save injected_secrets to EvoContext: {e}", exc_info=True
            )

    return HookResult(success=True, modified_context=context)


@hook_system.register(HookEvent.POST_TOOL_USE, matcher=".*", priority=100)
async def sensitive_file_censorship_gate(context: HookContext) -> HookResult:
    """
    Censor any raw secrets in tool outputs (stdout, stderr, returned dicts, etc.)
    by replacing them with '******'.
    """
    injected_secrets = context.extra.get("injected_secrets")
    # Fallback to EvoContext-scoped secrets if this hook context was reset between tool calls.
    if not injected_secrets:
        try:
            from app.core.context.manager import ContextManager

            ctx = ContextManager.current()
            ctx_secrets = ctx.injected_secrets
            if ctx_secrets:
                injected_secrets = list(ctx_secrets)
        except Exception as e:
            logger.debug(f"[CENSOR] Failed to read EvoContext injected_secrets: {e}")

    if not injected_secrets or not context.tool_result:
        return HookResult(success=True)

    sanitized = censor_tool_result(
        context.tool_result.output,
        context.tool_result.error,
        context.tool_result.data,
        set(injected_secrets),
    )
    context.tool_result.output = sanitized["output"]
    context.tool_result.error = sanitized["error"]
    context.tool_result.data = sanitized["data"]

    return HookResult(success=True, modified_context=context)
