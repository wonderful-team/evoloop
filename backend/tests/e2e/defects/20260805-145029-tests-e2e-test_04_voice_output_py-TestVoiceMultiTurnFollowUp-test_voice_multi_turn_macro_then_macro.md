# E2E 缺陷报告：test_voice_multi_turn_macro_then_macro

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceMultiTurnFollowUp::test_voice_multi_turn_macro_then_macro`
- **发现时间**: 2026-08-05T14:50:29.492049
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:193: in test_voice_multi_turn_macro_then_macro
    assert first["body"]["summary"] == "完成"
E   assert '好的，我听着呢。刚才这句...？您再说一下，我马上安排。' == '完成'
E     - 完成
E     + 好的，我听着呢。刚才这句话好像没听完整——您是想让我"对一下"什么内容？比如对账单、对数据、对文件？或者是有别的任务要交给我？您再说一下，我马上安排。
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
