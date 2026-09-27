# E2E 缺陷报告：test_l0_macro_trigger_routes_and_executes

- **测试 ID**: `tests/e2e/test_02_routing.py::TestL0MacroRoute::test_l0_macro_trigger_routes_and_executes`
- **发现时间**: 2026-08-05T23:46:25.900829
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_02_routing.py:204: in test_l0_macro_trigger_routes_and_executes
    assert body["status"] == "done", f"宏 L0 路由未正常完成: {body}"
E   AssertionError: 宏 L0 路由未正常完成: {'status': 'queued', 'thread_id': 'e2e-72a9c883611146f3', 'message_id': '4d2871ab-4d15-4020-ad77-f8c1918070f4'}
E   assert 'queued' == 'done'
E     - done
E     + queued
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_02_routing.py::TestL0MacroRoute::test_l0_macro_trigger_routes_and_executes -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
