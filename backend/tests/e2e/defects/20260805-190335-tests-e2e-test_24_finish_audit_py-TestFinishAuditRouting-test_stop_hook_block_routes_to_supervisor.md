# E2E 缺陷报告：test_stop_hook_block_routes_to_supervisor

- **测试 ID**: `tests/e2e/test_24_finish_audit.py::TestFinishAuditRouting::test_stop_hook_block_routes_to_supervisor`
- **发现时间**: 2026-08-05T19:03:35.049898
- **测试阶段**: Class
- **运行结果**: failed
- **失败类型**: call

## 预期行为

测试应通过，对应链路按文档描述正常返回数据。

## 实际行为

```
self = <tests.e2e.test_24_finish_audit.TestFinishAuditRouting object at 0x32609fb50>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x325460f10>

    async def test_stop_hook_block_routes_to_supervisor(self, monkeypatch) -> None:
        from app.core.engine.hooks.schemas import HookResult
    
        node = finish_mod.FinishNode(audit_service=_FakeAudit("COMPLETED"))
        _patch_node_db_deps(node)
        from app.core.engine import hooks as hooks_mod
    
        monkeypatch.setattr(
            hooks_mod.hook_system,
            "trigger",
            lambda *a, **k: HookResult(success=False, block=True, message="quality gate"),
        )
>       update = await node(_state(), {"configurable": {}})

tests/e2e/test_24_finish_audit.py:93: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <app.core.engine.nodes.finish.FinishNode object at 0x325fe5590>
state = AgentState(messages=[], tool_history=[], thread_id='t-finish', project_id=0, working_directory=None, session_goal='e2e...rences=None, situation_analysis=None, action_plan=None, clipboard=[], is_retry=None, iteration_count=0, next_node=None)
config = {'configurable': {}}

    async def __call__(self, state: "AgentState", config: dict) -> "StateUpdate":
        from app.core.engine.state import ensure_state
    
        state = ensure_state(state)
        try:
>           return await self._run(state, config)

app/core/engine/nodes/finish.py:41: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <app.core.engine.nodes.finish.FinishNode object at 0x325fe5590>
state = AgentState(messages=[], tool_history=[], thread_id='t-finish', project_id=0, working_directory=None, session_goal='e2e...rences=None, situation_analysis=None, action_plan=None, clipboard=[], is_retry=None, iteration_count=0, next_node=None)
config = {'configurable': {}}

    async def _run(self, state: "AgentState", config: dict) -> "StateUpdate":
        start_time = time.time()
    
        from app.core.context.manager import ContextManager
        from app.core.engine.hooks import HookContext, HookEvent, hook_system
        from app.core.engine.hooks.schemas import HookMetadata
    
        ctx = ContextManager.current()
        messages = state.messages
    
        effective_thread_id = (
            ctx.thread_id
            or state.thread_id
            or config.get("configurable", {}).get("thread_id")
        )
    
        if messages:
            model = config.get("configurable", {}).get("model")
            trim_result = _trimmer.trim(
                messages=messages,
                model=model,
                node_source="finish",
                stages={"window"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
                from app.core.engine.hooks import HookContext, HookEvent, hook_system
    
                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=effective_thread_id,
                        run_id=config.get("configurable", {}).get("run_id"),
                        messages=messages,
                        project_id=config.get("configurable", {}).get("project_id"),
                        member_id=config.get("configurable", {}).get("member_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    ),
                )
    
                logger.info(f"[Finish] Soft trim before audit: {trim_result.before_count} -> {trim_result.after_count} msgs")
            messages = trim_result.messages
    
        iteration_count = state.iteration_count or 0
        max_steps = settings.SUPERVISOR_AGENT_MAX_STEPS
        if state.max_supervisor_steps:
            max_steps = state.max_supervisor_steps
    
        is_shadow_mode = state.shadow_audit or False
        tool_history = state.tool_history or []
    
        await self._prepare_audit_input(state)
    
        service = self._audit_service or AuditService()
        audit_result: AuditResult = await service.execute(
            state=state,
            config=config,
            tool_history=tool_history,
            is_shadow_mode=is_shadow_mode,
        )
    
        summary = audit_result.summary
        final_outcome = audit_result.meta.get("outcome", "")
        macro_creation_eligible = (
            final_outcome.upper() == "COMPLETED"
>           and await self._has_replayable_steps(effective_thread_id)
        )
E       TypeError: object bool can't be used in 'await' expression

app/core/engine/nodes/finish.py:192: TypeError
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
