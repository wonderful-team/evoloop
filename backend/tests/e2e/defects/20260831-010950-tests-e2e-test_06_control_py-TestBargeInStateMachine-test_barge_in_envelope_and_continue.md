# E2E 缺陷报告：test_barge_in_envelope_and_continue

- **测试 ID**: `tests/e2e/test_06_control.py::TestBargeInStateMachine::test_barge_in_envelope_and_continue`
- **发现时间**: 2026-08-31T01:09:50.637388
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_06_control.TestBargeInStateMachine object at 0x1038b0890>
voice_conn = <tests.e2e.conftest.VoiceConn object at 0x1275f7f10>

    @pytest.mark.timeout(60)
    async def test_barge_in_envelope_and_continue(self, voice_conn: VoiceConn) -> None:
        """先 route（绑定线程）再 barge_in → voice.barge_in 信封，后续 route 仍可受理。"""
        await voice_conn.send_route("对的")
>       done_env = await voice_conn.wait_route_result(timeout=20.0)

tests/e2e/test_06_control.py:177: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <tests.e2e.conftest.VoiceConn object at 0x1275f7f10>, timeout = 20.0

    async def wait_route_result(self, timeout: float = 60.0) -> dict[str, Any]:
        env = await self._drain_until(
            lambda e: e.get("type") == "voice.route_result", timeout=timeout
        )
        if env is None:
>           raise TimeoutError(
                f"未收到 voice.route_result({timeout}s)，thread={self.thread_id}"
            )
E           TimeoutError: 未收到 voice.route_result(20.0s)，thread=e2e-fedc81cb9a74410d

tests/e2e/conftest.py:428: TimeoutError
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_06_control.py::TestBargeInStateMachine::test_barge_in_envelope_and_continue -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
