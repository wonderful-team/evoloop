# E2E 缺陷报告：test_voice_multi_turn_macro_then_macro

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceMultiTurnFollowUp::test_voice_multi_turn_macro_then_macro`
- **发现时间**: 2026-08-05T14:47:23.913544
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:191: in test_voice_multi_turn_macro_then_macro
    assert first["body"]["summary"] == "完成"
E   assert '你好，没太听清你的意思，...具体一点，我马上帮你处理。' == '完成'
E     - 完成
E     + 你好，没太听清你的意思，"麻烦对对对"是想让我对账、核对什么东西吗？比如核对账单、检查某个文件，还是之前提到的某个任务？麻烦再说具体一点，我马上帮你处理。
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceMultiTurnFollowUp::test_voice_multi_turn_macro_then_macro -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
