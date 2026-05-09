import asyncio
import functools
import json
import logging
import os

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as langchain_tool

from app.core.tools.schemas import EvoLoopToolConfig

logger = logging.getLogger(__name__)


class ToolResult(str):
    """工具返回值封装：给 Agent 的是纯文本 str，但附带元数据和渲染好的 display_name。"""

    def __new__(cls, text: str, meta: dict | None = None, display_name: str = ""):
        obj = super().__new__(cls, text)
        obj.meta = meta or {}
        obj.display_name = display_name
        return obj


def get_working_directory(config: RunnableConfig | None = None) -> str:
    """
    Extracts the working directory from the context or configuration.
    Prioritizes:
    1. Context variable 'working_directory'
    2. Config 'measurable' > 'working_directory' (Legacy)
    3. os.getcwd()
    """
    # 1. Check ContextVar
    from app.core.context.manager import ContextManager
    ctx = ContextManager.current()
    if ctx.working_directory:
        return ctx.working_directory

    # 2. Check RunnableConfig
    if config and "configurable" in config:
        wd = config["configurable"].get("working_directory")
        if wd:
            return wd

    # 3. Fallback to SystemConfig WORKSPACE_ROOT
    try:
        from app.infrastructure.config.service import SystemConfigService
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        if workspace_root:
            return workspace_root
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to fetch WORKSPACE_ROOT for tool fallback: {e}")

    # 4. Final Fallback
    return os.getcwd()


def evoloop_tool(
    *args,
    config: EvoLoopToolConfig | None = None,
    is_pollable: bool = False,
    is_state_mutating: bool = False,
    affected_path_keys: list[str] | None = None,
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
    # Build config from legacy kwargs when not provided explicitly
    if config is None:
        config = EvoLoopToolConfig(
            is_pollable=is_pollable,
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
        # 1. Permission check logic
        async def _check_permission(func_name, input_data):
            if config.required_benefit:
                from app.core.context.manager import ContextManager
                from app.services.benefit_service import benefit_service
                from app.core.config import settings

                ctx = ContextManager.current()
                if ctx.user_id:
                    try:
                        # Try to parse user_id as member_id and check benefit
                        member_id = int(ctx.user_id)
                        has_benefit = await benefit_service.has_benefit(
                            member_id, config.required_benefit
                        )
                        if not has_benefit:
                            from app.api.deps import create_benefit_error_detail
                            error_detail = create_benefit_error_detail(config.required_benefit)
                            from app.core.tools.schemas import ToolRegistryMetadata
                            metadata = ToolRegistryMetadata(summary_template=config.summary_template)
                            display_name = metadata.get_display_name(func_name, args=input_data)
                            return ToolResult(
                                json.dumps(error_detail.model_dump(), ensure_ascii=False),
                                meta={"status": "error", "error": "permission_denied"},
                                display_name=display_name
                            )
                    except Exception:
                        # In embedded/test mode, if benefit check fails due to infra,
                        # allow the tool to proceed (graceful degradation)
                        if not settings.EMBEDDED_MODE:
                            raise
                elif not settings.EMBEDDED_MODE:
                    from app.api.deps import create_benefit_error_detail
                    error_detail = create_benefit_error_detail(config.required_benefit)
                    from app.core.tools.schemas import ToolRegistryMetadata
                    metadata = ToolRegistryMetadata(summary_template=config.summary_template)
                    display_name = metadata.get_display_name(func_name, args=input_data)
                    return ToolResult(
                        json.dumps(error_detail.model_dump(), ensure_ascii=False),
                        meta={"status": "error", "error": "permission_denied"},
                        display_name=display_name
                    )
            return None

        # 2. Result processing logic (Standardization)
        def _process_result(result, func_name, input_data):
            result_meta = {}

            # Handle (content, meta) tuple
            if isinstance(result, tuple) and len(result) == 2:
                content, meta = result
                if isinstance(meta, dict):
                    result_meta = meta
                result = content

            # Extract meta from dict/model if not explicitly provided
            if not result_meta:
                if isinstance(result, dict):
                    for key in ["count", "id", "status", "path", "target"]:
                        if key in result:
                            result_meta[key] = result[key]
                elif hasattr(result, "model_dump"): # Pydantic v2
                    try:
                        data = result.model_dump()
                        for key in ["count", "id", "status", "path", "target"]:
                            if key in data:
                                result_meta[key] = data[key]
                    except Exception:
                        pass

            # Automatic Serialization to JSON
            if not isinstance(result, str):
                if hasattr(result, "model_dump_json"):
                    result = result.model_dump_json()
                elif isinstance(result, (dict, list)):
                    result = json.dumps(result, ensure_ascii=False)
                else:
                    result = str(result)

            # Render display_name and Wrap in ToolResult
            from app.core.tools.schemas import ToolRegistryMetadata
            metadata = ToolRegistryMetadata(summary_template=config.summary_template)
            display_name = metadata.get_display_name(func_name, args={**input_data, **result_meta})

            return ToolResult(result, meta=result_meta, display_name=display_name)

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args_f, **kwargs_f):
                # 提取 input_data 用于 display_name 渲染
                input_data = {k: v for k, v in kwargs_f.items() if k != "config" and not k.startswith("_")}
                
                # Check permission
                perm_error = await _check_permission(func.__name__, input_data)
                if perm_error:
                    return perm_error

                try:
                    result = await func(*args_f, **kwargs_f)
                    return _process_result(result, func.__name__, input_data)
                except Exception as e:
                    from app.core.tools.schemas import ToolRegistryMetadata
                    metadata = ToolRegistryMetadata(summary_template=config.summary_template)
                    display_name = metadata.get_display_name(func.__name__, args=input_data)
                    return ToolResult(f"Error: {str(e)}", meta={"status": "error", "error": str(e)}, display_name=display_name)
        else:
            @functools.wraps(func)
            def wrapper(*args_f, **kwargs_f):
                # 提取 input_data 用于 display_name 渲染
                input_data = {k: v for k, v in kwargs_f.items() if k != "config" and not k.startswith("_")}
                
                # Check permission (sync wrapper)
                if config.required_benefit:
                    # In a sync context, we need to run the async permission check
                    # We use a helper to ensure it runs correctly in the current event loop or a new one
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # This is risky if called from the main thread, but sync tools are 
                            # usually called from threads.
                            # For safety, we use a more robust way if asgiref is available, 
                            # but here we'll use a simple approach.
                            import threading
                            result_container = []
                            def run_in_thread():
                                try:
                                    res = asyncio.run(_check_permission(func.__name__, input_data))
                                    result_container.append(res)
                                except Exception as e:
                                    result_container.append(e)
                            
                            t = threading.Thread(target=run_in_thread)
                            t.start()
                            t.join()
                            perm_error = result_container[0]
                        else:
                            perm_error = asyncio.run(_check_permission(func.__name__, input_data))
                    except RuntimeError:
                        perm_error = asyncio.run(_check_permission(func.__name__, input_data))
                    
                    if isinstance(perm_error, Exception):
                        raise perm_error
                    if perm_error:
                        return perm_error

                try:
                    result = func(*args_f, **kwargs_f)
                    return _process_result(result, func.__name__, input_data)
                except Exception as e:
                    from app.core.tools.schemas import ToolRegistryMetadata
                    metadata = ToolRegistryMetadata(summary_template=config.summary_template)
                    display_name = metadata.get_display_name(func.__name__, args=input_data)
                    return ToolResult(f"Error: {str(e)}", meta={"status": "error", "error": str(e)}, display_name=display_name)

        # Mark for Auto-Discovery on the wrapper function
        wrapper.is_evoloop_active = True
        wrapper.evoloop_module = func.__module__
        # Apply LangChain's @tool (passing through any arguments)
        tool_instance = langchain_tool(*args, **kwargs)(wrapper)

        # Inject EvoLoop metadata for engine orchestration
        if tool_instance.metadata is None:
            tool_instance.metadata = {}

        tool_instance.metadata["is_pollable"] = config.is_pollable
        tool_instance.metadata["is_state_mutating"] = config.is_state_mutating
        tool_instance.metadata["affected_path_keys"] = config.affected_path_keys
        tool_instance.metadata["summary_template"] = config.summary_template
        tool_instance.metadata["is_memory_tool"] = config.is_memory_tool
        tool_instance.metadata["is_multimodal"] = config.is_multimodal
        tool_instance.metadata["is_hidden"] = config.is_hidden
        tool_instance.metadata["is_hitl"] = config.is_hitl

        # Enable error handling to return validation errors as text to the Agent
        # Note: HITL tools should set handle_tool_error=False to allow interrupt exceptions to propagate
        tool_instance.handle_tool_error = config.handle_tool_error

        return tool_instance

    # Handle both @evoloop_tool and @evoloop_tool(...)
    if len(args) == 1 and callable(args[0]):
        # Used as @evoloop_tool
        func = args[0]
        args = ()
        return decorator(func)
    else:
        # Used as @evoloop_tool(...)
        return decorator
