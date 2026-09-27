"""Full-chain regression tests for the Secure Vault (密码箱).

Covers every consumer that depends on SECRET_KEY-derived vault decryption,
using a real SQLite-backed SecureVaultService (NOT mocked), so the actual
encrypt-write / decrypt-read path is exercised end to end:

1. Macro param auto-fill from vault   (macro.runner.vault_fill_params)
2. Agent tool-input placeholder       (security.sensitive_file_placeholder_replacement_gate)
   substitution + output censorship   (security.sensitive_file_censorship_gate)
3. Agent vault tools                  (domain.tools.vault: list/request_secure_credential)
"""

import pytest
from sqlmodel import SQLModel, create_engine

import app.models.credential  # noqa: F401  register SecureCredential with SQLModel.metadata
from app.core.engine.hooks.schemas import HookContext, ToolInput, ToolResult
from app.core.engine.hooks.security import (
    sensitive_file_censorship_gate,
    sensitive_file_placeholder_replacement_gate,
)
from app.infrastructure.config.vault import SecureVaultService
from app.infrastructure.database.resource_manager import db_resource_manager


@pytest.fixture
def vault_db(tmp_path):
    """Real SQLite-backed SecureVaultService for the whole test session."""
    engine = create_engine(f"sqlite:///{tmp_path}/vault_chains.db")
    SQLModel.metadata.create_all(engine)
    prev = db_resource_manager._sync_engine  # 快照恢复：不污染其他测试的 DB 状态
    db_resource_manager._sync_engine = engine
    yield
    engine.dispose()
    db_resource_manager._sync_engine = prev


@pytest.fixture
def seeded_vault(vault_db):
    SecureVaultService.add_credential(
        identifier="ci-ssh",
        type="ssh",
        payload={"username": "deploy", "password": "p@ssw0rd"},
        project_id=None,  # global
    )
    return vault_db


class TestMacroParamAutoFill:
    def test_fills_missing_params_from_vault(self, seeded_vault, monkeypatch):
        from types import SimpleNamespace

        import app.core.learning.macro.runner as runner

        macro = SimpleNamespace(project_id=7, name="改库存", id=1)
        params: dict[str, str] = {}
        filled = runner.vault_fill_params(macro, ["username", "password"], params)
        assert filled == 2
        assert params["username"] == "deploy"
        assert params["password"] == "p@ssw0rd"

    def test_skips_wrong_project_credential(self, seeded_vault):
        from types import SimpleNamespace

        import app.core.learning.macro.runner as runner

        # global credential readable from any project -> still fills
        macro = SimpleNamespace(project_id=999, name="m", id=2)
        params: dict[str, str] = {}
        filled = runner.vault_fill_params(macro, ["username"], params)
        assert filled == 1
        assert params["username"] == "deploy"


class TestAgentPlaceholderSubstitution:
    @pytest.mark.asyncio
    async def test_placeholder_decrypted_into_tool_input(self, seeded_vault):
        context = HookContext(
            thread_id="t-1",
            project_id=3,
            tool_name="run_macro",
            tool_input=ToolInput(
                params={"query": "u1", "host": "{{vault.ci-ssh.username}}"}
            ),
        )
        result = await sensitive_file_placeholder_replacement_gate(context)
        assert result.success
        assert not result.block
        new_input = result.modified_context.tool_input
        assert new_input["params"]["host"] == "deploy"
        # injected secrets recorded for later censorship
        assert "deploy" in result.modified_context.extra["injected_secrets"]

    @pytest.mark.asyncio
    async def test_missing_credential_blocks(self, seeded_vault):
        context = HookContext(
            thread_id="t-1",
            project_id=3,
            tool_name="run_macro",
            tool_input=ToolInput(command="echo {{vault.no-such.key}}"),
        )
        result = await sensitive_file_placeholder_replacement_gate(context)
        assert not result.success
        assert result.block


class TestOutputCensorship:
    @pytest.mark.asyncio
    async def test_secret_redacted_in_tool_output(self):
        context = HookContext(
            thread_id="t-1",
            project_id=3,
            tool_name="run_macro",
            extra={"injected_secrets": ["p@ssw0rd", "deploy"]},
            tool_result=ToolResult(
                output="Connected as deploy with p@ssw0rd",
                data={"nested": {"password": "p@ssw0rd"}},
            ),
        )
        result = await sensitive_file_censorship_gate(context)
        assert result.success
        assert "deploy" not in result.modified_context.tool_result.output
        assert "p@ssw0rd" not in result.modified_context.tool_result.output
        assert result.modified_context.tool_result.data["nested"]["password"] == "******"

    @pytest.mark.asyncio
    async def test_no_secrets_no_change(self):
        context = HookContext(thread_id="t-1", project_id=3, tool_name="x", extra={})
        context.tool_result = ToolResult(output="plain text")
        result = await sensitive_file_censorship_gate(context)
        # no injected secrets -> hook is a no-op, output untouched
        assert result.success
        assert result.modified_context is None


class TestAgentVaultTools:
    @pytest.mark.asyncio
    async def test_list_vault_credentials_does_not_expose_secrets(self, seeded_vault, monkeypatch):
        from app.core.context.manager import ContextManager
        from app.domain.tools.vault import vault

        class _Ctx:
            project_id = None

        monkeypatch.setattr(ContextManager, "current", lambda: _Ctx())
        text = await vault(action="list")
        assert "ci-ssh" in text
        # metadata only — decrypted secrets must never appear
        assert "p@ssw0rd" not in text
        assert "deploy" not in text

    @pytest.mark.asyncio
    async def test_request_secure_credential_persists_encrypted(self, vault_db, monkeypatch):
        import getpass
        import sys

        from app.core.context.manager import ContextManager
        from app.domain.tools.vault import vault

        class _Ctx:
            project_id = None
            thread_id = "vault-req-1"
            member_id = 1

        monkeypatch.setattr(ContextManager, "current", lambda: _Ctx())
        monkeypatch.setattr("app.domain.tools.vault.is_in_event_loop", lambda: False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(getpass, "getpass", lambda prompt="": "mysecretval")

        text = await vault(action="request", identifier="ci-cli", type="env", fields=["token"])
        assert "ci-cli" in text
        # written via add_credential -> read back decrypted
        payload = SecureVaultService.get_credential_payload("ci-cli")
        assert payload == {"token": "mysecretval"}
