# E2E 缺陷报告：test_runs_all_steps_in_order_then_finish

- **测试 ID**: `tests/e2e/test_23_sequential_workflow.py::TestSequentialWorkflowNode::test_runs_all_steps_in_order_then_finish`
- **发现时间**: 2026-08-05T18:56:51.546880
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_23_sequential_workflow.py:103: in test_runs_all_steps_in_order_then_finish
    st1 = _state(plan, 0, [])
tests/e2e/test_23_sequential_workflow.py:56: in _state
    return AgentState(
E   pydantic_core._pydantic_core.ValidationError: 2 validation errors for AgentState
E   workflow_plan.0
E     Input should be an instance of LearnedSkill [type=is_instance_of, input_value=namespace(id='skill-1', name='Skill 1'), input_type=SimpleNamespace]
E       For further information visit https://errors.pydantic.dev/2.12/v/is_instance_of
E   workflow_plan.1
E     Input should be an instance of LearnedSkill [type=is_instance_of, input_value=namespace(id='skill-2', name='Skill 2'), input_type=SimpleNamespace]
E       For further information visit https://errors.pydantic.dev/2.12/v/is_instance_of
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
