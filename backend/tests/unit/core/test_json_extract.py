"""Unit tests for JSON extraction/repair (app/utils/extract.py).

Covers the multi-strategy JSON parsing used by decompose_task:
normal parsing, string-aware brace matching (instructions containing
literal braces), truncated/unterminated-string repair, markdown wrapping,
trailing commas, and surrounding-noise extraction.
"""

from __future__ import annotations

from app.utils.extract import safe_parse_json_value


class TestSafeParseJsonValue:
    def test_normal_list(self):
        assert safe_parse_json_value('[{"id": "sub-1", "instruction": "do a"}]') == [
            {"id": "sub-1", "instruction": "do a"}
        ]

    def test_string_aware_brace_matching(self):
        """instruction 内含字面 { } 不应破坏括号匹配（回归：Unterminated string 根因之一）。"""
        out = safe_parse_json_value(
            '[{"id": "sub-1", "instruction": "create plan {x} and {y}"}]'
        )
        assert out[0]["instruction"] == "create plan {x} and {y}"

    def test_unterminated_string_truncated(self):
        """截断输出：末尾未闭合字符串 + 未闭合括号 → 修复为完整 JSON。"""
        out = safe_parse_json_value('[{"id": "sub-1", "instruction": "stat app/core .py')
        assert out == [{"id": "sub-1", "instruction": "stat app/core .py"}]

    def test_markdown_wrapped(self):
        out = safe_parse_json_value('```json\n[{"id": "s0", "instruction": "x"}]\n```')
        assert out == [{"id": "s0", "instruction": "x"}]

    def test_trailing_comma(self):
        out = safe_parse_json_value('[{"id": "s0"},]')
        assert out == [{"id": "s0"}]

    def test_surrounding_noise(self):
        out = safe_parse_json_value(
            'Sure! Here is the JSON:\n[{"id": "s0", "instruction": "x"}]'
        )
        assert out == [{"id": "s0", "instruction": "x"}]

    def test_empty_or_invalid_returns_none(self):
        assert safe_parse_json_value("") is None
        assert safe_parse_json_value("not json at all") is None
