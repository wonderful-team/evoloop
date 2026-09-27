"""Integration tests for the security hook layer.

These tests exercise the real hook handlers with mocked Vault so that the
interaction between ``app.core.security.secrets`` and the hook framework is
covered end-to-end.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.engine.hooks.core import HookContext
from app.core.engine.hooks.schemas import ToolInput, ToolResult
from app.core.engine.hooks.security import (
    sensitive_file_censorship_gate,
    sensitive_file_placeholder_replacement_gate,
)


@pytest.fixture
def ctx_with_placeholder() -> HookContext:
    return HookContext(
        thread_id="t-1",
        run_id="r-1",
        project_id=120,
        tool_name="execute_command",
        tool_input=ToolInput.model_validate(
            {"command": "curl -H 'Authorization: {{vault.api.token}}' https://example.com"}
        ),
        tool_use_id="call-1",
    )


@pytest.mark.asyncio
async def test_placeholder_replacement_gate_injects_secret(ctx_with_placeholder):
    with patch(
        "app.core.security.secrets.SecureVaultService.get_credential_payload",
        return_value={"token": "super-secret-token"},
    ):
        result = await sensitive_file_placeholder_replacement_gate(ctx_with_placeholder)

    assert result.success is True
    assert result.block is False
    assert ctx_with_placeholder.tool_input is not None
    assert "super-secret-token" in ctx_with_placeholder.tool_input.command
    assert "{{vault.api.token}}" not in ctx_with_placeholder.tool_input.command
    assert "super-secret-token" in ctx_with_placeholder.extra["injected_secrets"]


@pytest.mark.asyncio
async def test_placeholder_replacement_gate_blocks_on_missing_credential(ctx_with_placeholder):
    with patch(
        "app.core.security.secrets.SecureVaultService.get_credential_payload",
        side_effect=KeyError("no such credential"),
    ):
        result = await sensitive_file_placeholder_replacement_gate(ctx_with_placeholder)

    assert result.success is False
    assert result.block is True
    assert "Failed to resolve secure placeholder" in (result.message or "")


@pytest.mark.asyncio
async def test_censorship_gate_masks_injected_secret(ctx_with_placeholder):
    ctx_with_placeholder.extra["injected_secrets"] = ["super-secret-token"]
    ctx_with_placeholder.tool_result = ToolResult(
        output="Response: super-secret-token",
        error="super-secret-token leaked",
        data={"token": "super-secret-token"},
    )

    result = await sensitive_file_censorship_gate(ctx_with_placeholder)

    assert result.success is True
    assert "super-secret-token" not in ctx_with_placeholder.tool_result.output
    assert "super-secret-token" not in (ctx_with_placeholder.tool_result.error or "")
    assert "super-secret-token" not in str(ctx_with_placeholder.tool_result.data)
    assert "******" in ctx_with_placeholder.tool_result.output


@pytest.mark.asyncio
async def test_censorship_gate_no_secrets_is_noop():
    ctx = HookContext(
        thread_id="t-1",
        run_id="r-1",
        tool_name="execute_command",
        tool_input=ToolInput.model_validate({"command": "echo hello"}),
        tool_use_id="call-1",
    )
    ctx.tool_result = ToolResult(output="hello", error=None, data=None)

    result = await sensitive_file_censorship_gate(ctx)

    assert result.success is True
    assert ctx.tool_result.output == "hello"
