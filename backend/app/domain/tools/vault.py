"""Secure Vault tool — single unified entry (密码箱 facade).

把 列凭据 / 请求录入 收敛为单一 ``vault`` 工具，按 ``action`` 分发，
与 ``macro`` facade 对齐：只读的 list 与写入的 request 共存于
同一工具，安全敏感行为由 SecureVaultService 与占位符钩子负责。
"""

import getpass
import logging
import sys
from typing import Annotated, Literal

from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.utils.async_utils import is_in_event_loop

logger = logging.getLogger(__name__)


@evoloop_tool(
    name="vault",
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.vault",
)
async def vault(
    action: Literal["list", "request"] = "list",
    type: str | None = None,
    identifier: str | None = None,
    fields: list[str] | None = None,
    description: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一密码箱（Secure Vault）入口——列出凭据或请求安全录入。

    Actions:
    - list:   列出当前项目上下文中可用的凭据标识、类型与描述。**不返回解密后的
              明文**，只返回元数据，让你知道哪些 {{vault.<id>.<field>}} 占位符可用。
    - request: 请求用户安全录入凭据（密码/私钥/API Key），加密存入 vault。
              录入后可立即用 {{vault.<identifier>.<field>}} 占位符引用。

    WHEN TO USE:
    - 工具入参需要密钥/口令，但还没存进 vault → list 看是否已有，没有则 request。
    - 需要把某个凭据写入 vault 供后续占位符替换 → request。

    Args:
        action: 执行的动作：
            - "list": 列出凭据标识/类型/描述（仅元数据，绝不返回解密后的密钥）。可选 type 过滤
              （ssh/env/password/api_key）。
            - "request": 提示用户安全录入凭据（密码/私钥/API Key）。需要 identifier、type、fields。
        identifier: 唯一凭据标识（如 "github_token"、"customer_a_ssh"）。
        type: 凭据类型（"ssh"、"env"、"password"、"api_key"）。用于 list 过滤或 request 类型。
        fields: request 需要的字段名列表（如 ["password"]、["private_key"]、["host", "password"]）。
        description: request 的可选原因说明（展示给用户）。
    """
    if action == "list":
        return await _list(type, config)
    return await _request(identifier, type, fields, description, config)


async def _list(type: str | None, config) -> str:
    """List credential identifiers/types/descriptions (metadata only)."""
    from app.infrastructure.config.vault import SecureVaultService

    ctx = ContextManager.current()
    project_id = ctx.project_id
    thread_id = _resolve_thread_id(config)
    logger.debug("[SecureVault] list called for thread %s (project %s)", thread_id, project_id)

    try:
        credentials = SecureVaultService.list_credentials(project_id=project_id)
        if type:
            credentials = [c for c in credentials if c["type"] == type]

        if not credentials:
            return "No credentials found in the Secure Vault for the current project context."

        output = ["### Available Secure Credentials in Vault:"]
        for c in credentials:
            project_desc = (
                f" (Project: {c['project_id']})" if c["project_id"] else " (Global)"
            )
            output.append(
                f"- **Identifier**: `{c['identifier']}` | **Type**: `{c['type']}`{project_desc}"
            )
            if c.get("description"):
                output.append(f"  *Description*: {c['description']}")
        return "\n".join(output)
    except Exception as e:
        logger.exception(f"Failed to list credentials: {e}")
        return f"Error listing credentials: {str(e)}"


async def _request(
    identifier: str | None,
    type: str | None,
    fields: list[str] | None,
    description: str | None,
    config,
) -> str:
    """Request the user to securely enter sensitive credentials."""
    if not identifier or not type or not fields:
        return (
            "Error: action=request requires `identifier`, `type`, and `fields`. "
            "Example: vault(action='request', identifier='github_token', "
            "type='api_key', fields=['token'])."
        )

    from app.infrastructure.config.vault import SecureVaultService

    ctx = ContextManager.current()
    project_id = ctx.project_id
    thread_id = _resolve_thread_id(config)
    logger.debug("[SecureVault] request called for thread %s (project %s)", thread_id, project_id)

    # Check if we are in an interactive TTY console (never block the server event loop on stdin)
    if not sys.stdin.isatty() or is_in_event_loop():
        logger.warning(f"[SecureVault] Non-interactive environment detected. Stdin prompt blocked for: {identifier}")
        return (
            f"[VAULT ERROR] Credential '{identifier}' is missing and cannot be requested interactively "
            f"because the agent is running in a non-interactive server environment.\n"
            f"Please direct the user to open the project's 'Vault' settings page in the UI and add the "
            f"credential identifier '{identifier}' with keys: {', '.join(fields)}."
        )

    logger.info(f"[HITL] Requesting credential entry for: {identifier} (Type: {type})")
    if description:
        logger.info(f"[HITL] Reason: {description}")
    logger.info(f"[HITL] Required Fields: {', '.join(fields)}")

    payload = {}
    for field in fields:
        prompt = f"Enter value for '{field}': "
        if (
            "pass" in field.lower()
            or "key" in field.lower()
            or "secret" in field.lower()
            or "token" in field.lower()
        ):
            try:
                val = getpass.getpass(prompt)
            except Exception:
                val = input(prompt)
        else:
            val = input(prompt)
        payload[field] = val

    try:
        SecureVaultService.add_credential(
            identifier=identifier,
            type=type,
            payload=payload,
            project_id=project_id,
            description=description,
        )
        return (
            f"✓ Credential '{identifier}' has been successfully saved to the Secure Vault.\n"
            f"You can now use it in tools using the placeholder: `{{{{vault.{identifier}.<field>}}}}`"
        )
    except Exception as e:
        logger.exception(f"Failed to save credential: {e}")
        return f"Error: Failed to save credential: {str(e)}"


def _resolve_thread_id(config) -> str:
    """Extract thread_id from the injected run config (dict or RunnableConfig)."""
    if not config:
        return ""
    if isinstance(config, dict):
        return config.get("configurable", {}).get("thread_id", "")
    return getattr(config, "configurable", {}).get("thread_id", "")
