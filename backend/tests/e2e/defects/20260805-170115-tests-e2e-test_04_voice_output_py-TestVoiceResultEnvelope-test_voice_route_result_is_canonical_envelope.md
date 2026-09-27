# E2E 缺陷报告：test_voice_route_result_is_canonical_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_route_result_is_canonical_envelope`
- **发现时间**: 2026-08-05T17:01:15.136557
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:94: in test_voice_route_result_is_canonical_envelope
    macro_id = await _safe_macro(http_client)
tests/e2e/test_04_voice_output.py:32: in _safe_macro
    await _wait_for_macro_in_spec(http_client, macro_id)
tests/e2e/test_02_routing.py:78: in _wait_for_macro_in_spec
    await wait_until(_check, timeout=timeout, desc=f"L0 spec 载入 macro:{macro_id}")
tests/e2e/conftest.py:87: in wait_until
    raise TimeoutError(f"等待超时({timeout}s): {desc}, last_value={last_value!r}")
E   TimeoutError: 等待超时(30.0s): L0 spec 载入 macro:536, last_value=False
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_route_result_is_canonical_envelope -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
