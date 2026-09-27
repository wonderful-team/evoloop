# E2E 缺陷报告：test_voice_done_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope`
- **发现时间**: 2026-08-05T14:50:48.259471
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:46: in test_voice_done_envelope
    assert body["summary"] == "完成"
E   assert '你好，我听到你说"对对对...下你的需求，我来帮你处理。' == '完成'
E     - 完成
E     + 你好，我听到你说"对对对"，但没太明白具体想做什么。你是想让我对账、核对什么东西，还是语音识别有误？请再说一下你的需求，我来帮你处理。
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
