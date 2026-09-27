# E2E 缺陷报告：test_runs_all_steps_in_order_then_finish

- **测试 ID**: `tests/e2e/test_23_sequential_workflow.py::TestSequentialWorkflowNode::test_runs_all_steps_in_order_then_finish`
- **发现时间**: 2026-08-05T18:57:39.203994
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_23_sequential_workflow.py:105: in test_runs_all_steps_in_order_then_finish
    u1 = await node(st1, {})
app/core/engine/nodes/sequential_workflow.py:89: in __call__
    await activity_monitor.update_agent_state(
E   TypeError: object NoneType can't be used in 'await' expression
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_23_sequential_workflow.py::TestSequentialWorkflowNode::test_runs_all_steps_in_order_then_finish -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
