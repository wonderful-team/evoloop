import functools
import json
import logging
import os

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as langchain_tool

from app.core.tools.schemas import EvoLoopToolConfig

logger = logging.getLogger(__name__)


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
    result_summary_template: str | None = None,
    is_memory_tool: bool = False,
    is_multimodal: bool = False,
    is_hidden: bool = False,  # Hide from user UI (internal control tools)
    handle_tool_error: bool = True,  # Allow override for HITL tools
    is_hitl: bool = False,  # If True, this tool triggers a human-in-the-loop request
    required_benefit: str | None = None,  # 权益编码，如 "desktop_control"
    **kwargs,
):
    """
    Decorator that applies standard EvoLoop tool behaviors.
    Can be used as @evoloop_tool or @evoloop_tool(name="...", is_pollable=True, ...).
    """
    import inspect

    # Build config from legacy kwargs when not provided explicitly
    if config is None:
        config = EvoLoopToolConfig(
            is_pollable=is_pollable,
            is_state_mutating=is_state_mutating,
            affected_path_keys=affected_path_keys or [],
            summary_template=summary_template,
            result_summary_template=result_summary_template,
            is_memory_tool=is_memory_tool,
            is_multimodal=is_multimodal,
            is_hidden=is_hidden,
            handle_tool_error=handle_tool_error,
            is_hitl=is_hitl,
            required_benefit=required_benefit,
        )

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args_f, **kwargs_f):
                # 权限检查
                from app.core.context.manager import ContextManager
                if config.required_benefit:
                    from app.api.deps import create_benefit_error_detail
                    from app.core.identity import identity_service

                    try:
                        from app.services.benefit_service import benefit_service

                        member_id = identity_service.get_member_id()
                        if not member_id:
                            # Fallback: try resolving from stored access token
                            access_token = identity_service.get_access_token()
                            if access_token:
                                member_id = await identity_service.resolve_member_id_from_token(access_token)
                        if not member_id:
                            return json.dumps({
                                "error": "Authentication required",
                                "code": "AUTH_REQUIRED",
                                "message": f"请先登录后再使用 {func.__name__} 功能"
                            }, ensure_ascii=False)

                        has_access = await benefit_service.has_benefit(member_id, config.required_benefit)
                        if not has_access:
                            # 使用统一的错误格式，与API层保持一致
                            error_detail = create_benefit_error_detail(config.required_benefit)
                            return json.dumps({
                                "error": "Benefit required",
                                "code": error_detail["code"],
                                "feature": error_detail["feature"],
                                "feature_name": error_detail["feature_name"],
                                "message": error_detail["message"],
                                "required_plan": error_detail["required_plan"],
                                "upgrade_url": error_detail["upgrade_url"]
                            }, ensure_ascii=False)
                    except (TypeError, ValueError, RuntimeError) as e:
                        logger.error(f"Permission check failed for {func.__name__}: {e}")
                        return json.dumps({
                            "error": "Permission check failed",
                            "code": "PERMISSION_CHECK_ERROR",
                            "message": f"权限检查失败: {str(e)}"
                        }, ensure_ascii=False)

                try:
                    return await func(*args_f, **kwargs_f)
                except Exception as e:
                    return f"Error: {str(e)}"
        else:

            @functools.wraps(func)
            def wrapper(*args_f, **kwargs_f):
                # 同步函数的权限检查（少见）
                if config.required_benefit:
                    return f"Error: {func.__name__} requires benefit {config.required_benefit} but sync tools don't support permission checks"

                try:
                    return func(*args_f, **kwargs_f)
                except Exception as e:
                    # Log error
                    return f"Error: {str(e)}"

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
        tool_instance.metadata["result_summary_template"] = config.result_summary_template
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
