"""
Security Hooks for EvoLoop.

Provides security gates for tool execution:
- Sudo command blocking
- Dangerous command detection
- Permission escalation prevention
"""

import logging
import re
from typing import Any

from app.core.engine.hooks.core import HookContext, HookEvent, HookResult, hook_system
from app.core.engine.hooks.schemas import ToolInput

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
            logger.warning(f"[SecurityHook] Blocked {cmd_type} command: {command[:100]}")
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
            logger.warning(f"[SecurityHook] Blocked dangerous {cmd_type} command: {command[:100]}")
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


@hook_system.register(
    HookEvent.PRE_TOOL_USE,
    matcher="^(view_file|grep_search|read_file|replace_file_content|multi_replace_file_content|write_to_file)$",
    priority=4,
)
async def project_metadata_protection_gate(context: HookContext) -> HookResult:
    """
    Protect project metadata (.evoloop directory) from agent access.

    Project_id -> local_path mappings and other metadata must not be altered or
    deleted by the agent.  Project-level sensitive files (e.g. .env) are now
    handled by the authorization_gate hook instead of being hard-blocked here.
    """
    tool_name = context.tool_name or ""
    tool_input = context.tool_input
    if not tool_input:
        return HookResult(success=True)

    paths_to_check = []
    if tool_input.path:
        paths_to_check.append(tool_input.path)
    if tool_input.args:
        for key in (
            "AbsolutePath",
            "TargetFile",
            "SearchPath",
            "TargetDirectory",
            "DirectoryPath",
        ):
            val = tool_input.args.get(key)
            if val and isinstance(val, str):
                paths_to_check.append(val)

    for path in paths_to_check:
        if ".evoloop" in path.lower():
            logger.warning(f"[SecurityHook] Blocked access to project metadata via {tool_name}: {path}")
            return HookResult(
                success=False,
                block=True,
                message=(
                    f"[SECURITY VIOLATION] Access Denied: Reading or modifying project metadata ({path}) is "
                    "prohibited to protect project identity and local path mappings."
                ),
            )

    if tool_name == "grep_search" and tool_input.args:
        search_path = tool_input.args.get("SearchPath") or ""
        if search_path and ".evoloop" in search_path.lower():
            logger.warning(f"[SecurityHook] Blocked grep search in project metadata: {search_path}")
            return HookResult(
                success=False,
                block=True,
                message="[SECURITY VIOLATION] Access Denied: Searching inside project metadata is prohibited.",
            )

    return HookResult(success=True)


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher=".*", priority=3)
async def sensitive_file_placeholder_replacement_gate(context: HookContext) -> HookResult:
    """
    Scan tool inputs recursively for {{vault.id.key}} placeholders, decrypt values,
    and substitute them in-place. Record injected raw values in context.extra for post-execution censorship.
    """
    tool_input = context.tool_input
    if not tool_input:
        return HookResult(success=True)

    from app.infrastructure.config.vault import SecureVaultService

    # Store decrypted secrets locally to avoid fetching multiple times and to use for post-execution mask
    decrypted_cache = {}
    injected_secrets = set()
    project_id = context.project_id

    # Pattern for {{vault.id.key}}
    pattern = re.compile(r"\{\{\s*vault\.([\w\-]+)\.([\w\-]+)\s*\}\}")

    def substitute_value(val: Any) -> Any:
        if isinstance(val, str):
            matches = list(pattern.finditer(val))
            if not matches:
                return val

            # Perform substitutions from right to left to avoid index shift issues
            new_val = val
            for match in reversed(matches):
                placeholder = match.group(0)
                identifier = match.group(1)
                key = match.group(2)

                try:
                    if identifier not in decrypted_cache:
                        decrypted_cache[identifier] = SecureVaultService.get_credential_payload(
                            identifier, project_id=project_id
                        )

                    payload = decrypted_cache[identifier]
                    if key in payload:
                        secret_value = str(payload[key])
                        injected_secrets.add(secret_value)
                        new_val = new_val.replace(placeholder, secret_value)
                    else:
                        logger.warning(f"[SecureVault] Key '{key}' not found in credential '{identifier}'")
                except (KeyError, PermissionError) as e:
                    raise ValueError(f"Failed to resolve secure placeholder {placeholder}: {e}")
            return new_val

        elif isinstance(val, dict):
            return {k: substitute_value(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [substitute_value(x) for x in val]
        return val

    try:
        # Substitute placeholders across ALL tool input fields (declared + dynamic
        # extra fields). The 5 legacy fields (command/path/content/query/args) only
        # cover a subset of tools; run_macro's `params`, browser_control's action
        # fields etc. live in dynamic extra fields and previously bypassed vault
        # injection, causing {{vault.*}} placeholders to reach the target literally.
        original_input = tool_input.model_dump()
        replaced = substitute_value(original_input)
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
            logger.warning(f"Failed to save injected_secrets to EvoContext: {e}", exc_info=True)

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
            logger.debug(f"[CENSOR] Failed to read EvoContext injected_secrets: {e}", exc_info=True)

    logger.info(f"[CENSOR DEBUG] injected_secrets={injected_secrets}, has_tool_result={context.tool_result is not None}, output={context.tool_result.output if context.tool_result else None}")
    if not injected_secrets or not context.tool_result:
        return HookResult(success=True)

    from typing import Any

    def sanitize_value(val: Any) -> Any:
        if isinstance(val, str):
            sanitized = val
            for secret in injected_secrets:
                if secret and secret in sanitized:
                    sanitized = sanitized.replace(secret, "******")
            return sanitized
        elif isinstance(val, dict):
            return {k: sanitize_value(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [sanitize_value(x) for x in val]
        return val

    # Sanitize outputs
    if context.tool_result.output:
        context.tool_result.output = sanitize_value(context.tool_result.output)
    if context.tool_result.error:
        context.tool_result.error = sanitize_value(context.tool_result.error)
    if context.tool_result.data:
        context.tool_result.data = sanitize_value(context.tool_result.data)

    return HookResult(success=True, modified_context=context)
