# E2E 缺陷报告：test_voice_multi_turn_macro_then_macro

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceMultiTurnFollowUp::test_voice_multi_turn_macro_then_macro`
- **发现时间**: 2026-08-05T15:49:36.213490
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
E   assert '好的，不过我这边听到的指...具体内容，我马上安排处理。' == '完成'
      - 完成
      + 好的，不过我这边听到的指令有点模糊，请问您是想让我"核对"什么内容呢？比如核对账目、代码、文件，还是别的事项？您再说一下具体内容，我马上安排处理。
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
