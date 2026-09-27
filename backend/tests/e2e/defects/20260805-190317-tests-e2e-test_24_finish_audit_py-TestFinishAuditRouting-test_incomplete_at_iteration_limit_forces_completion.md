# E2E 缺陷报告：test_incomplete_at_iteration_limit_forces_completion

- **测试 ID**: `tests/e2e/test_24_finish_audit.py::TestFinishAuditRouting::test_incomplete_at_iteration_limit_forces_completion`
- **发现时间**: 2026-08-05T19:03:17.420354
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
tests/e2e/test_24_finish_audit.py:78: in test_incomplete_at_iteration_limit_forces_completion
    assert update.next_node != RoutingTarget.SUPERVISOR
E   AssertionError: assert 'supervisor' != <RoutingTarget.SUPERVISOR: 'supervisor'>
E    +  where 'supervisor' = StateUpdate(messages=[], tool_history=[], thread_id=None, project_id=None, working_directory=None, session_goal=None, current_goal=None, ticket=None, verification=None, route_reason=None, worker_outcome='incomplete', summary=None, remaining_work=None, blocked_by_hook=None, current_plan=None, structured_plan=None, plan_approved=False, plan_progress=None, skill_execution_attempted=None, active_tool_profile=None, relevant_sops=[], workflow_results=None, workflow_plan=None, workflow_step_index=None, pending_signals=[], pending_approvals=[], shared_context={}, max_supervisor_steps=None, signal_queue_total=0, tool_memory=None, audit_tier=None, audit_meta=None, audit_input_data=None, audit_anomalies=[], final_outcome='INCOMPLETE', shadow_audit=None, termination_outcome=None, force_comprehensive_audit=None, test_failures=None, lint_errors=None, visited_nodes=[], workspace_context=None, execution_artifact=None, error=None, user_preferences=None, situation_analysis=None, action_plan=None, clipboard=[], next_node='supervisor', iteration_count=None, resume_tool_call=None).next_node
E    +  and   <RoutingTarget.SUPERVISOR: 'supervisor'> = RoutingTarget.SUPERVISOR
```

## 环境信息

- 服务地址: http://127.0.0.1:20160
- 测试账号: preterchan
- 测试会话 ID: 见测试日志

## 复现步骤

1. 启动后端服务: `cd evoloop/backend && ./bin/evo start`
2. 运行测试: `uv run pytest tests/e2e/test_24_finish_audit.py::TestFinishAuditRouting::test_incomplete_at_iteration_limit_forces_completion -v`

## 备注

本报告由 E2E 测试自动生成，需人工确认根因并补充分类（如 API 契约 / 路由 / 引擎 / 语音 / 移动网关等）。
