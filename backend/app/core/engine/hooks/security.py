"""
Security Hooks for EvoLoop.

Provides security gates for tool execution:
- Sudo command blocking
- Dangerous command detection
- Permission escalation prevention
"""

import logging
import re

from app.core.engine.hooks.core import hook_system, HookEvent, HookContext, HookResult

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
    command = context.tool_input.get("command", "")
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
                )
            )
    
    return HookResult(success=True)


@hook_system.register(HookEvent.PRE_TOOL_USE, matcher="^execute_command$", priority=6)
async def dangerous_command_gate(context: HookContext) -> HookResult:
    """
    Block potentially dangerous system commands.
    
    These commands may cause system instability or security risks.
    Priority 6 runs after elevated_privilege_gate.
    """
    command = context.tool_input.get("command", "")
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
                )
            )
    
    return HookResult(success=True)


logger.info("[SecurityHooks] Security hooks registered: elevated_privilege_gate, dangerous_command_gate")
