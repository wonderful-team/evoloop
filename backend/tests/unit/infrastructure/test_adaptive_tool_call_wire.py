"""Regression tests for _to_openai_tool_call (adaptive.py).

Production failure 2026-07-14: the voice-routed agent run executed
execute_command, then the second react-loop turn died with
``400 tokenization failed``. The EvoLoop gateway translates OpenAI→anthropic
and requires the standard function-wrapped tool_calls shape; adaptive.py was
passing the engine's native ``{index,id,name,args}`` shape through verbatim.
"""

import json

from app.infrastructure.llm.adaptive import _to_openai_tool_call


class TestToOpenAIToolCall:
    def test_native_shape_converted(self):
        tc = {"index": 1, "id": "tool_abc", "name": "execute_command",
              "args": {"command": "echo hi"}}
        out = _to_openai_tool_call(tc)
        assert out == {
            "id": "tool_abc",
            "type": "function",
            "function": {
                "name": "execute_command",
                "arguments": json.dumps({"command": "echo hi"}, ensure_ascii=False),
            },
        }

    def test_native_shape_string_args_passthrough(self):
        tc = {"index": 0, "id": "c1", "name": "demo", "args": '{"a":1}'}
        out = _to_openai_tool_call(tc)
        assert out["function"]["arguments"] == '{"a":1}'

    def test_already_standard_untouched(self):
        tc = {"id": "c2", "type": "function",
              "function": {"name": "demo", "arguments": "{}"}}
        assert _to_openai_tool_call(tc) is tc

    def test_missing_fields_default_empty(self):
        out = _to_openai_tool_call({})
        assert out == {"id": "", "type": "function",
                       "function": {"name": "", "arguments": ""}}

    def test_non_ascii_args_not_escaped(self):
        tc = {"id": "c3", "name": "demo", "args": {"q": "中文"}}
        out = _to_openai_tool_call(tc)
        assert "中文" in out["function"]["arguments"]
