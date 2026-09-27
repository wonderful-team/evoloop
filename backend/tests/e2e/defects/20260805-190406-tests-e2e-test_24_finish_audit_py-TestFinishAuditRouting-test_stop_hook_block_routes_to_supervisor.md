# E2E 缺陷报告：test_stop_hook_block_routes_to_supervisor

- **测试 ID**: `tests/e2e/test_24_finish_audit.py::TestFinishAuditRouting::test_stop_hook_block_routes_to_supervisor`
- **发现时间**: 2026-08-05T19:04:06.144767
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_24_finish_audit.py:97: in test_stop_hook_block_routes_to_supervisor
    update = await node(_state(), {"configurable": {}})
app/core/engine/nodes/finish.py:41: in __call__
    return await self._run(state, config)
app/core/engine/nodes/finish.py:231: in _run
    stop_result = await hook_system.trigger(HookEvent.STOP, stop_ctx, blocking=True)
E   TypeError: object HookResult can't be used in 'await' expression
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_24_finish_audit.py::TestFinishAuditRouting::test_stop_hook_block_routes_to_supervisor -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
