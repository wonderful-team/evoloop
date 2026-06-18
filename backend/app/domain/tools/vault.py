import logging
import sys
from typing import Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.context import ContextManager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.list_vault_credentials"
)
async def list_vault_credentials(
    type: Optional[str] = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    List all secure credential identifiers, types, and descriptions available in the Secure Vault
    for the current project context.
    
    This tool does NOT return the decrypted passwords, private keys, or secret payloads.
    It only returns metadata, letting you know what credential identifiers are available
    for placeholder substitution (e.g. {{vault.credential_id.field}}).
    
    Args:
        type: Optional filter by credential type (e.g. "ssh", "env", "password", "api_key").
    """
    from app.infrastructure.config.vault import SecureVaultService
    
    ctx = ContextManager.current()
    project_id = ctx.project_id
    
    try:
        credentials = SecureVaultService.list_credentials(project_id=project_id)
        if type:
            credentials = [c for c in credentials if c["type"] == type]
            
        if not credentials:
            return "No credentials found in the Secure Vault for the current project context."
            
        output = ["### Available Secure Credentials in Vault:"]
        for c in credentials:
            project_desc = f" (Project: {c['project_id']})" if c['project_id'] else " (Global)"
            output.append(f"- **Identifier**: `{c['identifier']}` | **Type**: `{c['type']}`{project_desc}")
            if c.get("description"):
                output.append(f"  *Description*: {c['description']}")
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Failed to list credentials: {e}")
        return f"Error listing credentials: {str(e)}"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.request_secure_credential"
)
async def request_secure_credential(
    identifier: str,
    type: str,
    fields: list[str],
    description: Optional[str] = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Request the user to securely enter sensitive credentials (passwords, private keys, API keys).
    
    This triggers a secure prompt where the user enters the secrets directly into the database vault.
    Once submitted, the credentials are saved encrypted in the vault, and you can use them using
    the placeholder format: {{vault.identifier.field_name}}.
    
    Args:
        identifier: The unique identifier for the credential (e.g. "customer_a_ssh", "github_token")
        type: The credential type ("ssh", "env", "password", "api_key")
        fields: The list of field names required (e.g. ["password"], ["private_key"], ["host", "password"])
        description: A brief explanation of why this credential is required.
    """
    from app.infrastructure.config.vault import SecureVaultService
    import getpass
    
    ctx = ContextManager.current()
    project_id = ctx.project_id
    
    # Check if we are in an interactive TTY console
    if not sys.stdin.isatty():
        logger.warning(f"[SecureVault] Non-interactive environment detected. Stdin prompt blocked for: {identifier}")
        return (
            f"[VAULT ERROR] Credential '{identifier}' is missing and cannot be requested interactively "
            f"because the agent is running in a non-interactive server environment.\n"
            f"Please direct the user to open the project's 'Vault' settings page in the UI and add the "
            f"credential identifier '{identifier}' with keys: {', '.join(fields)}."
        )
    
    print(f"\n🔑 [HITL REQUIRED] Requesting credential entry for: {identifier} (Type: {type})")
    if description:
        print(f"   Reason: {description}")
    print(f"   Required Fields: {', '.join(fields)}")
    
    payload = {}
    for field in fields:
        prompt = f"Enter value for '{field}': "
        if "pass" in field.lower() or "key" in field.lower() or "secret" in field.lower() or "token" in field.lower():
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
            description=description
        )
        return (
            f"✓ Credential '{identifier}' has been successfully saved to the Secure Vault.\n"
            f"You can now use it in tools using the placeholder: `{{{{vault.{identifier}.<field>}}}}`"
        )
    except Exception as e:
        logger.error(f"Failed to save credential: {e}")
        return f"Error: Failed to save credential: {str(e)}"
