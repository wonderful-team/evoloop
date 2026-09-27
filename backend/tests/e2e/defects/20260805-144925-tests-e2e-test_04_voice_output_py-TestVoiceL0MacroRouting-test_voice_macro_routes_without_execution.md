# E2E 缺陷报告：test_voice_macro_routes_without_execution

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceL0MacroRouting::test_voice_macro_routes_without_execution`
- **发现时间**: 2026-08-05T14:49:25.726337
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:174: in test_voice_macro_routes_without_execution
    assert body["summary"] == "完成"
E   assert '你好，我听到你说"对对对"，但不太确定你想让我做什么。请再说一下具体需求，比如查资料、写代码、操控电脑之类的，我马上帮你处理。' == '完成'
E     
E     - 完成
E     + 你好，我听到你说"对对对"，但不太确定你想让我做什么。请再说一下具体需求，比如查资料、写代码、操控电脑之类的，我马上帮你处理。
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_04_voice_output.py::TestVoiceL0MacroRouting::test_voice_macro_routes_without_execution -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
