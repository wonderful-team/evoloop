"""Unit tests for app.utils.redact."""

from __future__ import annotations

from app.utils.redact import (
    mask_sensitive_data,
    redact_secrets,
    sanitize_string,
)


class TestSanitizeString:
    def test_removes_control_characters(self):
        assert sanitize_string("hello\x00world") == "helloworld"

    def test_limits_length(self):
        assert len(sanitize_string("x" * 2000, max_length=100)) == 100

    def test_keeps_common_whitespace(self):
        assert sanitize_string("a\tb\nc\r") == "a\tb\nc\r"


class TestMaskSensitiveData:
    def test_masks_all_but_last_n_chars(self):
        assert mask_sensitive_data("secret1234", visible_chars=4) == "******1234"

    def test_masks_short_data_fully(self):
        assert mask_sensitive_data("123", visible_chars=4) == "***"


class TestRedactSecrets:
    def test_redacts_secret_in_string(self):
        assert redact_secrets("my secret is abc", ["abc"]) == "my secret is ******"

    def test_redacts_secret_in_dict(self):
        assert redact_secrets({"msg": "abc"}, ["abc"]) == {"msg": "******"}

    def test_redacts_secret_in_list(self):
        assert redact_secrets(["abc", "def"], ["abc"]) == ["******", "def"]

    def test_empty_secrets_returns_unchanged(self):
        assert redact_secrets("abc", []) == "abc"

    def test_does_not_mutate_input_container(self):
        original = {"msg": "abc"}
        result = redact_secrets(original, ["abc"])
        assert original["msg"] == "abc"
        assert result["msg"] == "******"

    def test_non_container_value_returns_unchanged(self):
        assert redact_secrets(42, ["abc"]) == 42
