# E2E 缺陷报告：test_voice_route_inbound_contract

- **测试 ID**: `tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract`
- **发现时间**: 2026-09-24T05:48:49.769024
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_01_inbound.py:137: in test_voice_route_inbound_contract
    assert body["summary"] == "完成"
E   AssertionError: assert '您想执行哪个宏？刚才「宏...说宏的名字，我来帮您执行。' == '完成'
E     - 完成
E     + 您想执行哪个宏？刚才「宏#」这个名字没有匹配到，目前宏库里有 50 个可用宏（音量、媒体控制、截屏、窗口、编辑、浏览器操作等）。
E     + 请告诉我具体要做什么，例如：
E     + 「截屏」：全屏截图到桌面
E     + 「打开应用」：打开指定应用
E     + 或者您想「对」什么（核对/比对）？
E     + 或者您直接说宏的名字，我来帮您执行。
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
