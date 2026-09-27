# E2E 缺陷报告：test_runs_all_steps_in_order_then_finish

- **测试 ID**: `tests/e2e/test_23_sequential_workflow.py::TestSequentialWorkflowNode::test_runs_all_steps_in_order_then_finish`
- **发现时间**: 2026-08-05T18:58:21.497228
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_23_sequential_workflow.TestSequentialWorkflowNode object at 0x30efd96d0>
_env = None
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x30ea51950>

    async def test_runs_all_steps_in_order_then_finish(self, _env, monkeypatch) -> None:
        engine = _FakeEngine(["out-1", "out-2"])
        monkeypatch.setattr(seq, "get_default_engine", lambda: engine)
        node = seq.SequentialWorkflowNode()
        plan = [_skill(1), _skill(2)]
    
        # 第 1 步
        st1 = _state(plan, 0, [])
>       u1 = await node(st1, {})

tests/e2e/test_23_sequential_workflow.py:109: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <app.core.engine.nodes.sequential_workflow.SequentialWorkflowNode object at 0x30f514990>
state = AgentState(messages=[], tool_history=[], thread_id='t', project_id=0, working_directory=None, session_goal='e2e-wf-goa...rences=None, situation_analysis=None, action_plan=None, clipboard=[], is_retry=None, iteration_count=0, next_node=None)
config = {}

    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        """Execute the next step of the sequential workflow."""
        plan = state.workflow_plan or []
        step_index = state.workflow_step_index or 0
        results = list(state.workflow_results or [])
    
        if step_index >= len(plan):
            logger.info(f"[SequentialWorkflow] All {len(plan)} steps completed.")
            return StateUpdate(
                messages=[AIMessage(content=f"Completed {len(plan)} step(s).")],
                next_node=RoutingTarget.FINISH,
            )
    
        skill = plan[step_index]
        is_last = step_index == len(plan) - 1
        skill_name = skill.name
        logger.info(f"[SequentialWorkflow] Step {step_index + 1}/{len(plan)}: {skill_name}")
    
        execution_ticket = state.ticket
        if not execution_ticket:
            logger.error("[SequentialWorkflow] Missing execution ticket")
            return StateUpdate(
                messages=[
                    AIMessage(
                        content="Sequential workflow failed: missing ticket.",
                        additional_kwargs={"is_error": True},
                    )
                ],
                next_node=RoutingTarget.SUPERVISOR,
            )
    
        agent_config = execution_ticket.agent_config
        role_name = agent_config.role_name if agent_config else "Worker"
    
        step_ticket = copy.deepcopy(execution_ticket)
        step_ticket.skill_ids = [skill.id] if skill.id else None
        step_ticket.topic = f"Step {step_index + 1}: {skill_name}"
    
        prompt_builder = WorkerPromptBuilder(
            agent_config=agent_config,
            blackboard=state,
            skills=[skill] if not isinstance(skill, list) else skill,
            ticket=step_ticket,
            focus_paths=[],
            plan=state.structured_plan or state.current_plan,
        )
        system_prompt = await prompt_builder.build(config)
    
        prev_output = results[-1].output if results else ""
        mission_msg = prompt_builder.build_mission_message(
            session_goal=state.session_goal,
            previous_output=prev_output,
        )
        messages = [HumanMessage(content=mission_msg)]
    
        from app.core.monitoring.activity import activity_monitor
    
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
>       await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="EXECUTING",
            task_name=f"Workflow Step {step_index + 1}/{len(plan)}",
            task_status=f"Executing skill: {skill_name}",
        )
E       TypeError: object NoneType can't be used in 'await' expression

app/core/engine/nodes/sequential_workflow.py:89: TypeError
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
