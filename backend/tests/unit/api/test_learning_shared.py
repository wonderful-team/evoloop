"""Regression tests for _normalize_json_list.

Production 500 on GET /learning/skills (2026-07-14): legacy rows store a
json.dumps string inside the JSON column (double-encoded), while newer rows
store native lists. The endpoint's bare ``json.loads`` crashed on native-list
rows. The normalizer must accept both forms.
"""

import json

from app.api.routes.learning._shared import _normalize_json_list


class TestNormalizeJsonList:
    def test_native_list_passthrough(self):
        assert _normalize_json_list(["a", "b"]) == ["a", "b"]

    def test_json_string_decoded(self):
        assert _normalize_json_list('["a", "b"]') == ["a", "b"]

    def test_double_encoded_string_decoded(self):
        """Legacy row shape: json.dumps output stored inside the JSON column,
        so the ORM returns a str that is itself JSON."""
        legacy = json.dumps(json.dumps(["触发词", "trigger"]))
        assert _normalize_json_list(legacy) == ["触发词", "trigger"]

    def test_none_and_empty(self):
        assert _normalize_json_list(None) == []
        assert _normalize_json_list("") == []
        assert _normalize_json_list([]) == []

    def test_garbage_returns_empty(self):
        assert _normalize_json_list("not json at all") == []

    def test_non_list_json_returns_empty(self):
        assert _normalize_json_list('{"a": 1}') == []
        assert _normalize_json_list(42) == []
