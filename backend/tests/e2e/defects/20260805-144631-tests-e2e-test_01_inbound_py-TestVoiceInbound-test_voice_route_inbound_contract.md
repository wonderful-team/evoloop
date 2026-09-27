# E2E 缺陷报告：test_voice_route_inbound_contract

- **测试 ID**: `tests/e2e/test_01_inbound.py::TestVoiceInbound::test_voice_route_inbound_contract`
- **发现时间**: 2026-08-05T14:46:31.533833
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_01_inbound.py:124: in test_voice_route_inbound_contract
    assert body["summary"] == "完成"
E   assert '你好，你说的"麻烦对对对...据、还是确认某个任务进度？' == '完成'
E     - 完成
E     + 你好，你说的"麻烦对对对"我有点没听明白，是语音识别出错了吗？请告诉我具体想做什么，比如核对文件、检查数据、还是确认某个任务进度？
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
