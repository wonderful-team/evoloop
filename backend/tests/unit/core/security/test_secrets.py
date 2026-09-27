"""Unit tests for app.core.security.secrets."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.security.secrets import (
    censor_tool_result,
    inject_secrets_into_tool_input,
    substitute_value,
)


class TestSubstituteValue:
    def test_no_placeholder_returns_unchanged(self):
        value, secrets = substitute_value("plain text")
        assert value == "plain text"
        assert secrets == set()

    def test_substitutes_single_placeholder(self):
        with patch(
            "app.core.security.secrets.SecureVaultService.get_credential_payload",
            return_value={"api_key": "super-secret"},
        ):
            value, secrets = substitute_value("key={{vault.my.api_key}}")
        assert value == "key=super-secret"
        assert secrets == {"super-secret"}

    def test_substitutes_multiple_placeholders_same_credential(self):
        with patch(
            "app.core.security.secrets.SecureVaultService.get_credential_payload",
            return_value={"a": "X", "b": "Y"},
        ):
            value, secrets = substitute_value({
                "cmd": "use {{vault.cred.a}} and {{vault.cred.b}}"
            })
        assert value["cmd"] == "use X and Y"
        assert secrets == {"X", "Y"}

    def test_missing_key_raises_value_error(self):
        with patch(
            "app.core.security.secrets.SecureVaultService.get_credential_payload",
            return_value={"other": "x"},
        ), pytest.raises(ValueError, match="Failed to resolve secure placeholder"):
            substitute_value("{{vault.my.api_key}}")

    def test_recurses_nested_structure(self):
        with patch(
            "app.core.security.secrets.SecureVaultService.get_credential_payload",
            return_value={"token": "T"},
        ):
            value, secrets = substitute_value([
                {"header": "Bearer {{vault.auth.token}}"},
                "no secret",
            ])
        assert value[0]["header"] == "Bearer T"
        assert secrets == {"T"}


@pytest.mark.asyncio
class TestInjectSecretsIntoToolInput:
    async def test_injects_secrets_into_tool_input_dict(self):
        with patch(
            "app.core.security.secrets.SecureVaultService.get_credential_payload",
            return_value={"key": "SECRET"},
        ):
            replaced, secrets = await inject_secrets_into_tool_input(
                {"command": "echo {{vault.cred.key}}"},
                project_id=120,
            )
        assert replaced["command"] == "echo SECRET"
        assert secrets == {"SECRET"}

    async def test_empty_dict_returns_empty_set(self):
        replaced, secrets = await inject_secrets_into_tool_input({})
        assert replaced == {}
        assert secrets == set()

    async def test_non_dict_substitution_result_raises(self):
        with patch(
            "app.core.security.secrets.substitute_value",
            return_value=("not-a-dict", set()),
        ), pytest.raises(ValueError, match="non-dict result"):
            await inject_secrets_into_tool_input({"command": "x"}, project_id=120)


class TestCensorToolResult:
    def test_censors_output_error_and_data(self):
        result = censor_tool_result(
            output="token=abc",
            error="abc failed",
            data={"msg": "abc"},
            secrets={"abc"},
        )
        assert result["output"] == "token=******"
        assert result["error"] == "****** failed"
        assert result["data"] == {"msg": "******"}

    def test_no_secrets_returns_unchanged(self):
        result = censor_tool_result(
            output="hello",
            error=None,
            data={"x": 1},
            secrets=None,
        )
        assert result == {"output": "hello", "error": None, "data": {"x": 1}}

    def test_empty_secrets_set_returns_unchanged(self):
        result = censor_tool_result("hello", None, None, set())
        assert result == {"output": "hello", "error": None, "data": None}
