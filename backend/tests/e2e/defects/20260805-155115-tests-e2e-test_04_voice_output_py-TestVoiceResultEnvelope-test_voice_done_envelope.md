# E2E 缺陷报告：test_voice_done_envelope

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceResultEnvelope::test_voice_done_envelope`
- **发现时间**: 2026-08-05T15:51:15.532419
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
E   assert '你好，我这边没听清你的需...、写代码、操作电脑都可以。' == '完成'
      - 完成
      + 你好，我这边没听清你的需求。"对对对"看起来像是误触或者语音没识别清楚，能再说一遍你想做什么吗？比如查资料、写代码、操作电脑都可以。
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
