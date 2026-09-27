"""MockLLM 单测：规则引擎、litellm 对象构造、SDK 流式聚合、patch 生命周期。"""

import pytest

from app.core.engine.sdk_adapter import mock_llm as mock_module
from app.core.engine.sdk_adapter.mock_llm import (
    MOCK_MODEL,
    _decide,
    _full_response,
    _stream_chunks,
    install,
    uninstall,
)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


@pytest.fixture(autouse=True)
def isolate_mock_env(monkeypatch):
    """与 .env 里的 E2E mock 开关隔离（进程 env 命中即优先于 .env 文件）。"""
    monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK", "")
    monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", "")


class TestDecideRules:
    def test_builtin_shell_fallback(self):
        decision = _decide([_msg("user", "帮我用 bash 执行 echo hello-world")])
        assert decision["tool"]["name"] == "bash"
        assert "echo" in decision["tool"]["arguments"]["command"]

    def test_builtin_tool_result_done(self):
        decision = _decide(
            [
                _msg("user", "echo hello"),
                {"role": "assistant", "content": None},
                {"role": "tool", "content": "hello-world"},
            ]
        )
        assert decision["text"].startswith("done:")
        assert "hello-world" in decision["text"]

    def test_builtin_echo_fallback(self):
        decision = _decide([_msg("user", "随便说点什么")])
        assert decision["text"].startswith("mock reply:")
        assert "随便说点什么" in decision["text"]

    def test_script_rule_tool(self, tmp_path, monkeypatch):
        script = tmp_path / "mock.json"
        script.write_text(
            '[{"when_contains": "write-marker",'
            ' "tool": {"name": "write", "arguments": {"path": "/tmp/x", "content": "hi"}}}]',
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        decision = _decide([_msg("user", "please write-marker now")])
        assert decision["tool"] == {
            "name": "write",
            "arguments": {"path": "/tmp/x", "content": "hi"},
        }

    def test_script_rule_tool_result(self, tmp_path, monkeypatch):
        script = tmp_path / "mock.json"
        script.write_text(
            '[{"when_tool_result": true, "text": "script-done"}]', encoding="utf-8"
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        messages = [
            _msg("user", "go"),
            {"role": "tool", "content": "raw output"},
        ]
        assert _decide(messages) == {"text": "script-done"}
        assert _decide([_msg("user", "go")])["text"].startswith("mock reply:")

    def test_script_rule_task_id_placeholder(self, tmp_path, monkeypatch):
        """{{task_id}} 占位符 → 替换为消息文本中的任务 uuid（duty 系统提示词）。"""
        script = tmp_path / "mock.json"
        script.write_text(
            '[{"when_contains": "write-marker", "when_not_tool_result": true,'
            ' "tool": {"name": "tasks", "arguments": {"action": "update_status",'
            ' "task_id": "{{task_id}}", "nested": {"also": "{{task_id}}", "keep": 1}}}}]',
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        messages = [
            _msg(
                "system",
                "任务元信息：\n- id: 4781a17f-884b-4e64-9f76-b9be8de96294\n- 状态: pending",
            ),
            _msg("user", "please write-marker now"),
        ]
        decision = _decide(messages)
        args = decision["tool"]["arguments"]
        assert args["task_id"] == "4781a17f-884b-4e64-9f76-b9be8de96294"
        assert args["nested"]["also"] == "4781a17f-884b-4e64-9f76-b9be8de96294"
        assert args["nested"]["keep"] == 1

    def test_script_rule_when_not_tool_result(self, tmp_path, monkeypatch):
        script = tmp_path / "mock.json"
        script.write_text(
            '[{"when_contains": "x", "when_not_tool_result": true, "text": "first"},'
            '{"when_tool_result": true, "text": "after"}]',
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        assert _decide([_msg("user", "do x")]) == {"text": "first"}
        messages = [_msg("user", "do x"), {"role": "tool", "content": "out"}]
        assert _decide(messages) == {"text": "after"}

    def test_script_rule_tool_result_contains(self, tmp_path, monkeypatch):
        script = tmp_path / "mock.json"
        script.write_text(
            '[{"when_tool_result_contains": "MAGIC", "text": "matched"}]',
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        hit = [_msg("user", "go"), {"role": "tool", "content": "has MAGIC inside"}]
        miss = [_msg("user", "go"), {"role": "tool", "content": "nothing"}]
        assert _decide(hit) == {"text": "matched"}
        assert _decide(miss) == {"text": "done: nothing"}

    def test_script_rule_reasoning(self, tmp_path, monkeypatch):
        script = tmp_path / "mock.json"
        script.write_text(
            '[{"when_contains": "think", "text": "ok", "reasoning": "hmm"}]',
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        decision = _decide([_msg("user", "please think about it")])
        assert decision == {"text": "ok", "reasoning": "hmm"}


class TestResponses:
    def test_full_response_text(self):
        resp = _full_response([_msg("user", "hi")], {"text": "hello"})
        assert resp.choices[0].message.content == "hello"
        assert resp.choices[0].finish_reason == "stop"
        assert resp.usage.total_tokens > 0

    def test_full_response_tool_call(self):
        decision = {"tool": {"name": "bash", "arguments": {"command": "ls"}}}
        resp = _full_response([_msg("user", "ls please")], decision)
        msg = resp.choices[0].message
        assert msg.content is None
        assert msg.tool_calls[0].function.name == "bash"
        assert resp.choices[0].finish_reason == "tool_calls"

    def test_stream_chunks_aggregate_via_sdk(self):
        from litellm import stream_chunk_builder

        messages = [_msg("user", "hi")]
        chunks = _stream_chunks(messages, {"text": "你好世界mock"})
        assert all(
            getattr(chunk.choices[0].delta, "content", None) is not None
            or chunk.choices[0].finish_reason
            for chunk in chunks
        )
        merged = stream_chunk_builder(chunks, messages=messages)
        assert "你好世界mock" in merged.choices[0].message.content
        assert merged.usage.total_tokens > 0

    def test_stream_chunks_tool_call(self):
        from litellm import stream_chunk_builder

        messages = [_msg("user", "ls")]
        decision = {"tool": {"name": "bash", "arguments": {"command": "ls"}}}
        merged = stream_chunk_builder(chunks=_stream_chunks(messages, decision), messages=messages)
        assert merged.choices[0].message.tool_calls[0].function.name == "bash"


class TestPatchLifecycle:
    def test_install_uninstall(self):
        import openhands.sdk.llm.llm as sdk_llm_mod

        # 前置套件可能留下已安装的 mock；先 uninstall 确保基线干净。
        uninstall()
        orig_completion = sdk_llm_mod.litellm_completion
        orig_acompletion = sdk_llm_mod.litellm_acompletion
        try:
            install()
            assert sdk_llm_mod.litellm_completion is mock_module._render_sync
            assert sdk_llm_mod.litellm_acompletion is mock_module._render_async
            install()  # 幂等
            assert sdk_llm_mod.litellm_completion is mock_module._render_sync
        finally:
            uninstall()
        assert sdk_llm_mod.litellm_completion is orig_completion
        assert sdk_llm_mod.litellm_acompletion is orig_acompletion

    @pytest.mark.anyio
    async def test_async_render_returns_response(self):
        install()
        try:
            result = await sdk_llm_mod_call()
            assert result.choices[0].message.content.startswith("mock reply:")
        finally:
            uninstall()


async def sdk_llm_mod_call():
    import openhands.sdk.llm.llm as sdk_llm_mod

    return await sdk_llm_mod.litellm_acompletion(
        messages=[{"role": "user", "content": "anything"}], stream=False
    )


def test_mock_model_name():
    assert MOCK_MODEL.startswith("openai/")


class TestSequenceRules:
    def test_sequence_replay_and_created_placeholders(self, tmp_path, monkeypatch):
        """sequence 规则：按 (规则, 任务) 计数回放多步；{{created_N}} 串血统。"""
        import json as _json

        script = tmp_path / "mock.json"
        script.write_text(
            _json.dumps(
                [
                    {
                        "when_contains": "plan-marker",
                        "sequence": [
                            {
                                "tool": {
                                    "name": "tasks",
                                    "arguments": {"action": "create", "title": "根1"},
                                }
                            },
                            {
                                "tool": {
                                    "name": "tasks",
                                    "arguments": {
                                        "action": "create",
                                        "title": "子A",
                                        "parent_id": "{{created_1}}",
                                        "dependencies": ["{{created_1}}"],
                                    },
                                }
                            },
                            {
                                "tool": {
                                    "name": "tasks",
                                    "arguments": {
                                        "action": "create",
                                        "title": "子B",
                                        "parent_id": "{{created_1}}",
                                        "dependencies": ["{{created_2}}"],
                                    },
                                }
                            },
                        ],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOLOOP_SDK_LLM_MOCK_SCRIPT", str(script))
        sys_msg = {
            "role": "system",
            "content": "- id: 4781a17f-884b-4e64-9f76-b9be8de96294",
        }
        user_msg = _msg("user", "请 plan-marker 出图谱")

        d1 = _decide([sys_msg, user_msg])
        assert d1["tool"]["arguments"]["title"] == "根1"

        root_result = {
            "role": "tool",
            "content": _json.dumps(
                {
                    "success": True,
                    "id": "66dead35-4a1d-4cf4-8a33-cd3ca7bc7d2b",
                    "task_no": 2,
                }
            ),
        }
        d2 = _decide(
            [sys_msg, user_msg, {"role": "assistant", "content": None}, root_result]
        )
        assert d2["tool"]["arguments"]["parent_id"] == (
            "66dead35-4a1d-4cf4-8a33-cd3ca7bc7d2b"
        )

        sub_result = {
            "role": "tool",
            "content": _json.dumps(
                {
                    "success": True,
                    "id": "6e11ee53-d8d2-40ca-a5c7-73b33b637dd7",
                    "task_no": 3,
                }
            ),
        }
        d3 = _decide(
            [
                sys_msg,
                user_msg,
                {"role": "assistant", "content": None},
                root_result,
                {"role": "assistant", "content": None},
                sub_result,
            ]
        )
        a3 = d3["tool"]["arguments"]
        assert a3["parent_id"] == "66dead35-4a1d-4cf4-8a33-cd3ca7bc7d2b"
        assert a3["dependencies"] == ["6e11ee53-d8d2-40ca-a5c7-73b33b637dd7"]

        d4 = _decide(
            [
                sys_msg,
                user_msg,
                {"role": "assistant", "content": None},
                root_result,
                {"role": "assistant", "content": None},
                sub_result,
                {"role": "assistant", "content": None},
                sub_result,
            ]
        )
        assert d4["tool"]["arguments"]["title"] == "子B"
