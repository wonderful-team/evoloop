"""Adapters from EvoLoop native tools to OpenHands SDK tools."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
import threading
from typing import Any
from uuid import uuid4

from app.core.engine.state import AgentState
from app.core.engine.tools.executor import AgentToolExecutor
from app.core.exceptions import AgentHumanInterruptException

_ADAPTERS: dict[tuple[str, str], Any] = {}
_ADAPTERS_LOCK = threading.RLock()
_REGISTRY_TOOL_CLASS: type | None = None
_REGISTERED_NAMES: set[str] = set()

# NOTE: the SDK registry resolver is `RegistryTool.create`, which pulls the
# CURRENT executor out of ``_ADAPTERS`` at resolve time — so registering a
# tool name once is enough even though each delivery rebuilds adapters with
# fresh state/config. Re-registering per delivery only produces
# "Duplicate tool name" noise on every turn.
logger = logging.getLogger(__name__)


def _tool_schema(tool: Any) -> dict[str, Any]:
    raw_schema = getattr(tool, "raw_args_schema", None)
    if isinstance(raw_schema, dict) and raw_schema:
        return raw_schema

    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None:
        model_json_schema = getattr(args_schema, "model_json_schema", None)
        if callable(model_json_schema):
            candidate = model_json_schema()
            if isinstance(candidate, dict):
                return candidate

    func = getattr(tool, "func", None)
    if func is not None and callable(func):
        return _schema_from_signature(func)

    return {"type": "object", "properties": {}, "additionalProperties": True}


_JSON_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _schema_from_signature(func: Any) -> dict[str, Any]:
    """Derive a JSON schema from the tool function signature.

    Most @evoloop_tool tools declare no args_schema; the legacy kernel derived
    the wire schema from the signature (bind_tools). Mirrors that: annotations
    map to JSON types, params without defaults are required, and the injected
    ``config`` parameter is excluded.
    """

    import inspect
    import typing

    properties: dict[str, Any] = {}
    required: list[str] = []

    try:
        # eval_str=True 解析字符串化注解（``from __future__ import annotations``
        # 的模块所有注解都是 str，Literal/类型映射会全部落空）。
        signature = inspect.signature(func, eval_str=True)
    except (TypeError, ValueError, NameError):
        return {"type": "object", "properties": {}, "additionalProperties": True}

    for name, param in signature.parameters.items():
        if name == "config":
            continue  # injected runtime context, not an LLM-visible argument
        annotation = param.annotation
        if typing.get_origin(annotation) is typing.Annotated:
            annotation = typing.get_args(annotation)[0]

        prop: dict[str, Any] = {}
        if annotation is typing.Literal or (
            typing.get_origin(annotation) is typing.Literal
        ):
            values = typing.get_args(annotation)
            prop = {"type": "string", "enum": [str(v) for v in values]}
        elif annotation in _JSON_TYPE_MAP:
            prop = {"type": _JSON_TYPE_MAP[annotation]}
        else:
            prop = {}

        description = ""
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            description = ""

        if description:
            prop["description"] = description
        properties[name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _tool_description(tool: Any) -> str:
    return str(getattr(tool, "description", None) or getattr(tool, "name", ""))


def _build_sdk_tool(
    tool: Any,
    *,
    loop: asyncio.AbstractEventLoop,
    native_executor: AgentToolExecutor,
    tool_history: list[str],
):
    from openhands.sdk.tool.client_tool import (
        ClientTool,
        ClientToolObservation,
        ClientToolSpec,
    )
    from openhands.sdk.tool.tool import ToolExecutor

    class NativeToolExecutor(ToolExecutor):
        """Run the existing async executor from an SDK worker thread."""

        def __init__(self) -> None:
            self._interrupted = False
            # worker 线程里 contextvar 不继承请求上下文；run_coroutine_threadsafe
            # 若不带快照，工具执行侧 ContextManager.current() 会读到全局残留
            # ctx（跨 thread 的 working_directory/能力装配污染）。构建时捕获。
            self._ctx_snapshot = contextvars.copy_context()

        def interrupt(self) -> None:
            self._interrupted = True

        def __call__(self, action: Any, conversation: Any = None):
            if self._interrupted:
                return ClientToolObservation.from_text(
                    text="Tool call cancelled by interrupt.", is_error=True
                )

            args = action.model_dump(exclude_none=True)
            args.pop("kind", None)
            args.pop("security_risk", None)
            args.pop("summary", None)
            try:
                future = self._ctx_snapshot.run(
                    asyncio.run_coroutine_threadsafe,
                    native_executor.execute_tool(
                        tool_name=str(tool.name),
                        tool_args=args,
                        tool_id=str(uuid4()),
                        local_tool_history=tool_history,
                    ),
                    loop,
                )
                result = future.result()
                return ClientToolObservation.from_text(text=str(result.message.content))
            except AgentHumanInterruptException:
                return self._wait_for_resume(conversation)

        def _wait_for_resume(self, conversation: Any):
            """Wait on the existing ThreadGate without touching SDK state locks."""

            from app.core.engine.session.manager import session_manager

            thread_id = str(
                native_executor.config.get("configurable", {}).get("thread_id")
            )
            session = session_manager.get(thread_id)
            if session is None:
                raise RuntimeError(
                    "HITL tool interruption requires a resident AgentSession"
                )

            while not self._interrupted:
                async def _next_event():
                    return await asyncio.wait_for(session.gate.wait_next(), timeout=2.0)

                event_future = asyncio.run_coroutine_threadsafe(_next_event(), loop)
                try:
                    event = event_future.result()
                except concurrent.futures.TimeoutError:
                    event_future.cancel()
                    check = asyncio.run_coroutine_threadsafe(
                        self._check_cancellation(thread_id), loop
                    )
                    try:
                        check.result()
                    except Exception:
                        if conversation is not None:
                            conversation.interrupt()
                        return ClientToolObservation.from_text(
                            text="Tool call cancelled while waiting for human input.",
                            is_error=True,
                        )
                    continue

                payload = event.payload or {}
                if event.kind in ("session_cancel", "session_close"):
                    if conversation is not None:
                        conversation.interrupt()
                    return ClientToolObservation.from_text(
                        text="Tool call cancelled while waiting for human input.",
                        is_error=True,
                    )
                if event.kind != "user_message":
                    continue

                user_input = payload.get("hitl_resume_response")
                if user_input is None:
                    raw = payload.get("inputs")
                    if isinstance(raw, dict):
                        user_input = raw.get("session_goal") or raw.get("goal")
                    elif raw is not None:
                        user_input = getattr(raw, "session_goal", None) or getattr(
                            raw, "goal", None
                        )
                if user_input is None:
                    continue

                resume = asyncio.run_coroutine_threadsafe(
                    self._resume_hitl(
                        thread_id=thread_id,
                        user_input=str(user_input),
                        grant_mode=payload.get("grant_mode"),
                    ),
                    loop,
                )
                return ClientToolObservation.from_text(text=str(resume.result()))

            return ClientToolObservation.from_text(
                text="Tool call cancelled by interrupt.", is_error=True
            )

        async def _check_cancellation(self, thread_id: str) -> None:
            from app.core.monitoring.activity import activity_monitor

            await activity_monitor.check_cancellation(thread_id)

        async def _resume_hitl(
            self, *, thread_id: str, user_input: str, grant_mode: str | None
        ) -> str:
            from app.core.context.manager import ContextManager
            from app.core.hitl.orchestrator import HITLOrchestrator

            model = native_executor.config.get("configurable", {}).get("model")
            pending = await HITLOrchestrator.get_pending_request(thread_id, model)
            if pending is None:
                return user_input
            normalized, claimed = await HITLOrchestrator.handle_resume(
                thread_id, pending, user_input, grant_mode=grant_mode
            )
            if not claimed:
                return user_input
            final_result = await HITLOrchestrator.resolve_approved_tool_result(
                pending,
                native_executor.config,
                normalized,
                state=native_executor.state,
                grant_mode=grant_mode,
                thread_id=thread_id,
            )
            ctx = ContextManager.current()
            await HITLOrchestrator.persist_hitl_user_message(
                thread_id=thread_id,
                project_id=ctx.project_id,
                member_id=ctx.member_id or 0,
                tool_call_id=pending["id"],
                user_content=user_input,
                final_result=final_result,
            )
            return final_result

    name = str(tool.name)
    spec = ClientToolSpec(
        name=name,
        description=_tool_description(tool),
        parameters=_tool_schema(tool),
    )
    return ClientTool.from_spec(spec).set_executor(NativeToolExecutor())


def _registry_tool_class():
    global _REGISTRY_TOOL_CLASS
    if _REGISTRY_TOOL_CLASS is not None:
        return _REGISTRY_TOOL_CLASS

    from openhands.sdk.tool.client_tool import ClientTool, ClientToolSpec
    from openhands.sdk.tool.registry import register_tool
    from openhands.sdk.tool.schema import Action, Observation
    from openhands.sdk.tool.tool import ToolDefinition

    class RegistryTool(ToolDefinition[Action, Observation]):
        @classmethod
        def create(_cls, conv_state: Any = None, **params):
            if conv_state is None:
                raise ValueError("OpenHands conversation state is required")
            conversation_id = str(conv_state.id)
            tool_name = str(params["tool_name"])
            with _ADAPTERS_LOCK:
                executor = _ADAPTERS[(conversation_id, tool_name)]
            spec = ClientToolSpec.model_validate(params["spec"])
            return [ClientTool.from_spec(spec).set_executor(executor)]

    _REGISTRY_TOOL_CLASS = RegistryTool
    register_tool("evoloop_sdk_registry", RegistryTool)
    return RegistryTool


async def build_sdk_tools(
    state: AgentState,
    config: dict[str, Any],
    *,
    loop: asyncio.AbstractEventLoop,
    tool_history: list[str],
    conversation_id: str,
):
    """Resolve the existing capability surface and wrap it once."""

    from app.core.tools.manager import tool_manager

    native_tools = await tool_manager.get_agent_tools("react", state)
    from openhands.sdk.tool.registry import register_tool
    from openhands.sdk.tool.spec import Tool as SDKToolSpec
    from openhands.sdk.tool.tool import ToolDefinition

    from app.core.config import settings

    allowed = (config.get("metadata") or {}).get("subagent_tools")
    if allowed:
        allowed_names = set(allowed)
        native_tools = [tool for tool in native_tools if tool.name in allowed_names]

    hitl_tools = [
        str(tool.name)
        for tool in native_tools
        if bool(getattr(tool, "metadata", {}).get("is_hitl"))
        or settings.TOOL_PERMISSIONS.get(str(tool.name)) == "ask"
    ]
    thread_id = str((config.get("configurable") or {}).get("thread_id") or "")
    if hitl_tools:
        from app.core.engine.session.manager import session_manager

        if not thread_id or session_manager.get(thread_id) is None:
            native_tools = [
                tool
                for tool in native_tools
                if str(tool.name) not in set(hitl_tools)
            ]
            logger.warning(
                "SDK direct run has no resident session; hiding HITL tools: %s",
                sorted(hitl_tools),
            )

    native_tools_to_wrap = [
        tool for tool in native_tools if not isinstance(tool, ToolDefinition)
    ]
    prebuilt_sdk_tools = [
        tool for tool in native_tools if isinstance(tool, ToolDefinition)
    ]
    if prebuilt_sdk_tools:
        from app.core.engine.sdk_adapter import SDKAdapterError

        raise SDKAdapterError(
            "OpenHands SDK MCP/prebuilt ToolDefinition bridging is not enabled yet: "
            f"{sorted(str(tool.name) for tool in prebuilt_sdk_tools)}"
        )

    sdk_tools: list[SDKToolSpec] = []
    registry_tool = _registry_tool_class()
    native_executor = AgentToolExecutor(
        tool_map={tool.name: tool for tool in native_tools_to_wrap},
        state=state,
        config=config,
        name="SDKAgent",
        enable_diff_tracking=True,
    )
    for tool in native_tools_to_wrap:
        name = str(tool.name)
        spec = {
            "name": name,
            "description": _tool_description(tool),
            "parameters": _tool_schema(tool),
        }
        adapter = _build_sdk_tool(
            tool,
            loop=loop,
            native_executor=native_executor,
            tool_history=tool_history,
        ).executor
        with _ADAPTERS_LOCK:
            _ADAPTERS[(conversation_id, name)] = adapter
        if name not in _REGISTERED_NAMES:
            register_tool(name, registry_tool)
            _REGISTERED_NAMES.add(name)
        sdk_tools.append(
            SDKToolSpec(
                name=name,
                params={"tool_name": name, "spec": spec},
            )
        )
    return sdk_tools
