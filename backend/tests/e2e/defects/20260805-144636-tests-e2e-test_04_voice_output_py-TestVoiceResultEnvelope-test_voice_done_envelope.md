# E2E 缺陷报告：test_voice_done_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope`
- **发现时间**: 2026-08-05T14:46:36.850122
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:44: in test_voice_done_envelope
    assert body["summary"] == "完成"
E   AssertionError: assert '好的，请问您想让我做什么...是其他任务？请具体说一下。' == '完成'
E     - 完成
E     + 好的，请问您想让我做什么呢？比如对一下账、核对某个文件，还是其他任务？请具体说一下。
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
