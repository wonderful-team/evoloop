"""Secrets injection and censorship for tool inputs/outputs.

Provides two main capabilities used by the security hook layer:

1. Substituting ``{{vault.id.key}}`` placeholders in tool inputs with decrypted
   values from ``SecureVaultService``.
2. Censoring any raw secret values that leak into tool outputs.

The module intentionally operates on plain Python containers (dict/list/str) so
that it does not depend on the hook framework itself.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.infrastructure.config.vault import SecureVaultService
from app.utils.redact import redact_secrets

logger = logging.getLogger(__name__)

# Pattern for {{vault.id.key}}
_VAULT_PLACEHOLDER_RE = re.compile(r"\{\{\s*vault\.([\w\-]+)\.([\w\-]+)\s*\}\}")


def _placeholder_secret_value(
    placeholder: str,
    identifier: str,
    key: str,
    project_id: int | None,
    decrypted_cache: dict[str, dict[str, Any]],
) -> str:
    """Resolve a single vault placeholder to its secret value."""
    try:
        if identifier not in decrypted_cache:
            decrypted_cache[identifier] = SecureVaultService.get_credential_payload(
                identifier, project_id=project_id
            )

        payload = decrypted_cache[identifier]
        if key in payload:
            return str(payload[key])

        logger.warning(
            f"[SecureVault] Key '{key}' not found in credential '{identifier}'"
        )
        raise KeyError(f"Key '{key}' not found in credential '{identifier}'")
    except (KeyError, PermissionError) as e:
        raise ValueError(
            f"Failed to resolve secure placeholder {placeholder}: {e}"
        ) from e


def substitute_value(
    value: Any,
    project_id: int | None = None,
    decrypted_cache: dict[str, dict[str, Any]] | None = None,
    injected_secrets: set[str] | None = None,
) -> tuple[Any, set[str]]:
    """Recursively substitute vault placeholders inside ``value``.

    Returns the substituted value and the set of raw secrets that were injected.
    """
    if decrypted_cache is None:
        decrypted_cache = {}
    if injected_secrets is None:
        injected_secrets = set()

    if isinstance(value, str):
        matches = list(_VAULT_PLACEHOLDER_RE.finditer(value))
        if not matches:
            return value, injected_secrets

        new_val = value
        for match in reversed(matches):
            placeholder = match.group(0)
            identifier = match.group(1)
            key = match.group(2)

            secret_value = _placeholder_secret_value(
                placeholder, identifier, key, project_id, decrypted_cache
            )
            injected_secrets.add(secret_value)
            new_val = new_val.replace(placeholder, secret_value)
        return new_val, injected_secrets

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            new_v, injected_secrets = substitute_value(
                v, project_id, decrypted_cache, injected_secrets
            )
            result[k] = new_v
        return result, injected_secrets

    if isinstance(value, list):
        result_list: list[Any] = []
        for item in value:
            new_item, injected_secrets = substitute_value(
                item, project_id, decrypted_cache, injected_secrets
            )
            result_list.append(new_item)
        return result_list, injected_secrets

    return value, injected_secrets


async def inject_secrets_into_tool_input(
    tool_input_dict: dict[str, Any],
    project_id: int | None = None,
) -> tuple[dict[str, Any], set[str]]:
    """Substitute vault placeholders across a raw tool input dictionary.

    Returns the substituted dictionary and the set of raw secrets injected.
    Raises ``ValueError`` if a placeholder cannot be resolved.
    """
    decrypted_cache: dict[str, dict[str, Any]] = {}
    injected_secrets: set[str] = set()
    replaced, injected_secrets = substitute_value(
        tool_input_dict, project_id, decrypted_cache, injected_secrets
    )
    if not isinstance(replaced, dict):
        # Tool input is always expected to be a dict; fail-fast if substitution
        # somehow changed the top-level type.
        raise ValueError("Tool input substitution produced a non-dict result")
    return replaced, injected_secrets


def censor_tool_result(
    output: Any,
    error: Any,
    data: dict[str, Any] | None,
    secrets: set[str] | None,
) -> dict[str, Any]:
    """Replace any known secrets in a tool result with ``******``.

    Returns a dict with keys ``output``, ``error``, ``data``.
    """
    if not secrets:
        return {"output": output, "error": error, "data": data}

    secrets_list = list(secrets)
    return {
        "output": redact_secrets(output, secrets_list),
        "error": redact_secrets(error, secrets_list),
        "data": redact_secrets(data, secrets_list),
    }
