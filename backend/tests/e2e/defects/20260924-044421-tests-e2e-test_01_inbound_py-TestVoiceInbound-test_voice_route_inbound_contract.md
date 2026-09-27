# E2E 缺陷报告：test_voice_route_inbound_contract

- **测试 ID**: `tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract`
- **发现时间**: 2026-09-24T04:44:21.202701
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_01_inbound.py:131: in test_voice_route_inbound_contract
    assert body["summary"] == "完成"
E   AssertionError: assert '我看了下可用宏列表，没有...宏\n告诉我具体需求即可。' == '完成'
E     - 完成
E     + 我看了下可用宏列表，没有叫「宏#」或「对」的宏（失败是因为名称不存在）。
E     + 请问你实际想做什么？我可以帮你：
E     + 运行某个已有宏（列表在上面，如静音、截屏、打开应用等）
E     + 或者把某个重复操作录成新宏
E     + 告诉我具体需求即可。
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
