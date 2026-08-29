import asyncio
import functools
import inspect
import json
import logging
import os
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.core.tools.schemas import EvoLoopToolConfig

logger = logging.getLogger(__name__)


class ToolResult(str):
    """工具返回值封装：给 Agent 的是纯文本 str，但附带元数据和渲染好的 display_name。"""

    def __new__(cls, text: str, meta: dict | None = None, display_name: str = ""):
        obj = super().__new__(cls, text)
        obj.meta = meta or {}
        obj.display_name = display_name
        return obj


def get_working_directory(config: dict | None = None) -> str:
    """
    Extracts the working directory from the context or configuration.
    """
    from app.core.context.manager import ContextManager

    ctx = ContextManager.current()
    if ctx.working_directory:
        return ctx.working_directory

    if config and "configurable" in config:
        wd = config["configurable"].get("working_directory")
        if wd:
            return wd
        # 工具执行时 config 一定带 thread_id；用它查 thread_store 的
        # working_directory（project 级路径），避免 ctx.thread_id 为 None
        # 时误 fallback 到 WORKSPACE_ROOT，导致 Agent 探索范围越出项目。
        tid = config["configurable"].get("thread_id")
        if tid:
            try:
                from app.core.context import thread_context_store

                managed_cwd = thread_context_store.get_working_directory(tid)
                if managed_cwd:
                    return managed_cwd
            except Exception as e:
                logger.warning(f"Failed to fetch working directory from thread_context_store: {e}", exc_info=True)

    if ctx.thread_id:
        try:
            from app.core.context import thread_context_store

            managed_cwd = thread_context_store.get_working_directory(ctx.thread_id)
            if managed_cwd:
                return managed_cwd
        except Exception as e:
            logger.warning(f"Failed to fetch working directory from thread_context_store: {e}", exc_info=True)

    try:
        from app.core.project.utils import get_workspace_root

        workspace_root = get_workspace_root()
        if workspace_root:
            return workspace_root
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to fetch WORKSPACE_ROOT for tool fallback: {e}", exc_info=True)

    return os.getcwd()


class StructuredTool:
    """Mock StructuredTool for runtime compatibility with dynamic tools."""

    def __init__(self, func, name: str, description: str):
        self.func = func
        self.name = name
        self.description = description
        self.coroutine = func if inspect.iscoroutinefunction(func) else None
        self.metadata = {}
        self.handle_tool_error = True

    @classmethod
    def from_function(cls, func, name: str, description: str) -> "StructuredTool":
        return cls(func, name, description)

    async def ainvoke(self, args: Any, config: dict | None = None) -> Any:
        kwargs = {}
        if isinstance(args, dict):
            kwargs.update(args)
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        return self.func(**kwargs)


class EvoLoopTool(StructuredTool):
    """
    A native, SDK-free tool implementation serving as the native tool base class.
    """

    def __init__(self, func, name: str = None, description: str = None, args_schema: Any = None):
        self.func = func
        self.coroutine = func if inspect.iscoroutinefunction(func) else None
        self.name = name or func.__name__
        self.description = description or func.__doc__ or ""
        self.args_schema = args_schema
        self.metadata = {}
        self.handle_tool_error = True
        self.affected_path_extractor = None

        sig = inspect.signature(func)
        self._accepts_config = "config" in sig.parameters

    async def ainvoke(self, args: Any, config: dict | None = None) -> Any:
        kwargs = {}
        if isinstance(args, dict):
            kwargs.update(args)
        if self._accepts_config:
            kwargs["config"] = config

        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        else:
            return self.func(**kwargs)

    def invoke(self, args: Any, config: dict | None = None) -> Any:
        kwargs = {}
        if isinstance(args, dict):
            kwargs.update(args)
        if self._accepts_config:
            kwargs["config"] = config

        if inspect.iscoroutinefunction(self.func):
            raise RuntimeError("Cannot invoke coroutine synchronously")
        return self.func(**kwargs)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


def evoloop_tool(
    *args,
    config: EvoLoopToolConfig | None = None,
    is_state_mutating: bool = False,
    affected_path_keys: list[str] | None = None,
    affected_path_extractor: Callable | None = None,
    summary_template: str | None = None,
    is_memory_tool: bool = False,
    is_multimodal: bool = False,
    is_hidden: bool = False,
    handle_tool_error: bool = True,
    is_hitl: bool = False,
    required_benefit: str | None = None,
    **kwargs,
):
    """
    Decorator that applies standard EvoLoop tool behaviors.
    """
    if config is None:
        config = EvoLoopToolConfig(
            is_state_mutating=is_state_mutating,
            affected_path_keys=affected_path_keys or [],
            summary_template=summary_template,
            is_memory_tool=is_memory_tool,
            is_multimodal=is_multimodal,
            is_hidden=is_hidden,
            handle_tool_error=handle_tool_error,
            is_hitl=is_hitl,
            required_benefit=required_benefit,
        )

    def decorator(func):
        async def _check_permission(func_name, input_data):
            if config.required_benefit:
                from app.core.benefits import (
                    benefit_service,
                    create_benefit_error_detail,
                )
                from app.core.config import settings
                from app.core.context.manager import ContextManager

                ctx = ContextManager.current()
                if ctx.member_id:
                    try:
                        has_benefit = await benefit_service.has_benefit(
                            ctx.member_id, config.required_benefit
                        )
                        if not has_benefit:
                            error_detail = create_benefit_error_detail(config.required_benefit)
                            display_name = config.get_display_name(func_name, args=input_data)
                            return ToolResult(
                                json.dumps(error_detail.model_dump(), ensure_ascii=False),
                                meta={"status": "error", "error": "permission_denied"},
                                display_name=display_name,
                            )
                    except Exception:
                        if not settings.EMBEDDED_MODE:
                            raise
                elif not settings.EMBEDDED_MODE:
                    error_detail = create_benefit_error_detail(config.required_benefit)
                    display_name = config.get_display_name(func_name, args=input_data)
                    return ToolResult(
                        json.dumps(error_detail.model_dump(), ensure_ascii=False),
                        meta={"status": "error", "error": "permission_denied"},
                        display_name=display_name,
                    )
            return None

        def _process_result(result, func_name, input_data):
            result_meta = {}

            if isinstance(result, tuple) and len(result) == 2:
                content, meta = result
                if isinstance(meta, dict):
                    result_meta = meta
                result = content

            if not result_meta:
                if isinstance(result, dict):
                    for key in ["count", "id", "status", "path", "target"]:
                        if key in result:
                            result_meta[key] = result[key]
                elif isinstance(result, BaseModel):
                    try:
                        data = result.model_dump()
                        for key in ["count", "id", "status", "path", "target"]:
                            if key in data:
                                result_meta[key] = data[key]
                    except Exception as e:
                        logger.debug("Suppressed error: %s", e, exc_info=True)

            if not isinstance(result, str):
                if isinstance(result, BaseModel):
                    result = result.model_dump_json()
                elif isinstance(result, (dict, list)):
                    result = json.dumps(result, ensure_ascii=False)
                else:
                    result = str(result)

            display_name = config.get_display_name(func_name, args={**input_data, **result_meta})

            return ToolResult(result, meta=result_meta, display_name=display_name)

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args_f, **kwargs_f):
                input_data = {k: v for k, v in kwargs_f.items() if k != "config" and not k.startswith("_")}
                perm_error = await _check_permission(func.__name__, input_data)
                if perm_error:
                    return perm_error

                try:
                    result = await func(*args_f, **kwargs_f)
                    return _process_result(result, func.__name__, input_data)
                except Exception as e:
                    display_name = config.get_display_name(func.__name__, args=input_data)
                    return ToolResult(f"Error: {str(e)}", meta={"status": "error", "error": str(e)}, display_name=display_name)
        else:

            @functools.wraps(func)
            def wrapper(*args_f, **kwargs_f):
                input_data = {k: v for k, v in kwargs_f.items() if k != "config" and not k.startswith("_")}
                try:
                    result = func(*args_f, **kwargs_f)
                    return _process_result(result, func.__name__, input_data)
                except Exception as e:
                    display_name = config.get_display_name(func.__name__, args=input_data)
                    return ToolResult(f"Error: {str(e)}", meta={"status": "error", "error": str(e)}, display_name=display_name)

        wrapper.is_evoloop_active = True
        wrapper.evoloop_module = func.__module__

        tool_instance = EvoLoopTool(
            wrapper,
            name=kwargs.get("name"),
            description=kwargs.get("description"),
            args_schema=kwargs.get("args_schema"),
        )

        tool_instance.affected_path_extractor = affected_path_extractor
        tool_instance.metadata["is_state_mutating"] = config.is_state_mutating
        tool_instance.metadata["affected_path_keys"] = config.affected_path_keys
        tool_instance.metadata["summary_template"] = config.summary_template
        tool_instance.metadata["is_memory_tool"] = config.is_memory_tool
        tool_instance.metadata["is_multimodal"] = config.is_multimodal
        tool_instance.metadata["is_hidden"] = config.is_hidden
        tool_instance.metadata["is_hitl"] = config.is_hitl

        tool_instance.handle_tool_error = config.handle_tool_error

        return tool_instance

    if len(args) == 1 and callable(args[0]):
        func = args[0]
        args = ()
        return decorator(func)
    else:
        return decorator


# Marker for arguments injected dynamically by the agent runtime
InjectedToolArg = object
