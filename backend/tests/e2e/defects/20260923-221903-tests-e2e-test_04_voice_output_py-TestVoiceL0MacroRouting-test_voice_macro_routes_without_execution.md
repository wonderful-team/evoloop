# E2E 缺陷报告：test_voice_macro_routes_without_execution

- **测试 ID**: `tests/e2e/test_04_voice_output.py::TestVoiceL0MacroRouting::test_voice_macro_routes_without_execution`
- **发现时间**: 2026-09-23T22:19:03.668975
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_04_voice_output.py:178: in test_voice_macro_routes_without_execution
    assert body["summary"] == "完成"
E   assert '宏库里没有叫「对对对」或...我来判断。\n你想做什么？' == '完成'
E     - 完成
E     + 宏库里没有叫「对对对」或「宏#」的宏，所以执行失败。
E     + 你可以告诉我：
E     + 想执行上面列表里的哪个宏（比如"截屏""清空废纸篓"），或者
E     + 直接用一句话描述想做的事，我来判断。
E     + 你想做什么？
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
