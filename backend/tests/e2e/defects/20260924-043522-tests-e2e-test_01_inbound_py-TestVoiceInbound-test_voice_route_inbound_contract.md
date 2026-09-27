# E2E 缺陷报告：test_voice_route_inbound_contract

- **测试 ID**: `tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract`
- **发现时间**: 2026-09-24T04:35:22.193442
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_01_inbound.py:131: in test_voice_route_inbound_contract
    assert body["summary"] == "完成"
E   assert '宏列表里没有叫「宏#」的...诉我具体需求，我马上处理。' == '完成'
E     - 完成
E     + 宏列表里没有叫「宏#」的宏（这名字像是占位符/系统自动填入的，不是真实宏名）。当前有 50 个宏可用，比如：静音、音量调整、锁屏、息屏、截屏、播放控制、窗口管理、剪贴板操作等。
E     + "麻烦对对对"我不太确定你的意思，请确认你想做什么：
E     + 想执行某个具体宏？请告诉我宏的名字（比如"截屏""锁屏"）。
E     + 还是想核对/验证某件事？
E     + 告诉我具体需求，我马上处理。
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
