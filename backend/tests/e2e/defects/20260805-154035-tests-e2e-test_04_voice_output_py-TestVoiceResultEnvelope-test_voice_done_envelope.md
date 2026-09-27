# E2E 缺陷报告：test_voice_done_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope`
- **发现时间**: 2026-08-05T15:40:35.939937
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:40: in test_voice_done_envelope
    ) -> None:
tests/e2e/test_04_voice_output.py:28: in _safe_macro
    spec_trigger = f"e2e_ack_{uuid.uuid4().hex[:8]}"
tests/e2e/test_02_routing.py:77: in _wait_for_macro_in_spec
    ???
tests/e2e/conftest.py:87: in wait_until
    raise TimeoutError(f"等待超时({timeout}s): {desc}, last_value={last_value!r}")
E   TimeoutError: 等待超时(30.0s): L0 spec 载入 macro:523, last_value=False
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
