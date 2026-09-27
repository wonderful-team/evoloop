"""Verification of get_token → extract_bearer_token merge (incl. bug fix)."""

from __future__ import annotations

from app.api.deps import extract_bearer_token


class TestExtractBearerToken:
    def test_none_and_empty_return_none(self) -> None:
        assert extract_bearer_token(None) is None
        assert extract_bearer_token("") is None

    def test_bearer_stripped(self) -> None:
        assert extract_bearer_token("Bearer abc123") == "abc123"
        assert extract_bearer_token("Bearer   spaced-token  ") == "  spaced-token  "

    def test_non_bearer_returned_unchanged(self) -> None:
        # The _modules.py copy previously dropped this branch (returned None).
        # This test pins the merged semantics.
        assert extract_bearer_token("raw-token") == "raw-token"
        assert extract_bearer_token("Basic dXNlcjpwYXNz") == "Basic dXNlcjpwYXNz"
