# E2E 缺陷报告：test_voice_route_text_pipeline[tool-route]

- **测试 ID**: `tests/e2e/real/test_real_voice.py::TestRealVoiceClient::test_voice_route_text_pipeline[tool-route]`
- **发现时间**: 2026-08-29T05:26:15.389860
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/real/test_real_voice.py:109: in test_voice_route_text_pipeline
    result = await conn.wait_terminal_route_result(timeout=90.0)
tests/e2e/conftest.py:449: in wait_terminal_route_result
    raise TimeoutError(
E   TimeoutError: 未收到终态 voice.route_result(90.0s)，thread=e2e-2a165ee589664007
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/real/test_real_voice.py::TestRealVoiceClient::test_voice_route_text_pipeline[tool-route] -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
