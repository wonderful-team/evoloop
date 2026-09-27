# E2E 缺陷报告：test_supervisor_comfort_routed_envelope

- **测试 ID**: `tests/e2e/test_18_voice_reply_points.py::TestVoiceReplyPoints::test_supervisor_comfort_routed_envelope`
- **发现时间**: 2026-08-29T06:00:20.936442
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_18_voice_reply_points.py:135: in test_supervisor_comfort_routed_envelope
    assert terminal is not None, (
E   AssertionError: 150s 内未收到任何 voice.route_result 终态，thread=e2e-799dc372842d45ca
E   assert None is not None
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_18_voice_reply_points.py::TestVoiceReplyPoints::test_supervisor_comfort_routed_envelope -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
