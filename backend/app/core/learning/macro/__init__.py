"""EvoLoop 宏引擎 — 标准化公共 API 门面（惰性导出）。

对外统一入口：核心执行 / 生命周期 / 编译 / 创建 / 迁移 / 工具 / 事件均通过此门面导出。
外部模块应从这里导入，而不是深入底层子模块。

标准约定：
- 唯一门面：``from app.core.learning.macro import MacroService, list_macros, ...``
- 不允许外部直接 import 带下划线的私有符号（``_xxx``）。

实现说明：使用模块级 ``__getattr__`` 惰性导出。``__init__`` 本身不加载任何重模块，
符号在首次被 ``from app.core.learning.macro import X`` 引用时才加载对应子模块，
避免底层基础设施（如 events.publishers）import 宏包时把整个执行引擎拉进加载链造成循环依赖。
"""

from __future__ import annotations

import importlib

__all__ = [
    # 执行入口 / 执行准备
    "MacroEngine",
    "resolve_project_base_url",
    "is_navigation_macro",
    "get_navigation_info",
    "vault_fill_params",
    "invalidate_macro_cache",
    "VOICE_POLICY",
    "WEB_POLICY",
    "ExecutionOutcome",
    "MacroGateError",
    # 生命周期
    "list_macros",
    "load_macro",
    "load_verified_macro",
    "find_macro_by_name",
    "list_active_macro_index",
    "create_macro_from_synthesis",
    "persist_native_macros",
    "confirm_macro",
    "confirm_bulk",
    "update_macro",
    "delete_macro",
    "purge_obsolete_macros",
    "downgrade_macro",
    "mark_obsolete_by_app_map",
    "obsolete_macro",
    "macro_to_yaml",
    # 编译 / 创建 / 迁移
    "MacroScriptCompiler",
    "MacroCreatorService",
    # 任务 / 工具
    "native_macro_maintenance",
    "resurvey_and_regen",
    "verify_safe_native_macros",
    "configured_apps",
    "verify_macro_script",
    "cleanup_macro_steps",
    # 服务 / 创作门禁
    "MacroService",
    "validate_script",
    "validate_macro_structure",
    "extract_navigation_url",
    # 事件 / 模型
    "MacroMutatedEvent",
    "MacroScript",
    "MacroStep",
    "MacroRunResult",
    "MacroVerificationResult",
    "MacroSource",
    "MacroStepType",
]

# 导出符号 -> 所属子模块（惰性加载目标）
_SYMBOL_MODULES: dict[str, str] = {
    # 执行入口 / 执行准备
    "MacroEngine": "app.core.learning.macro.engine",
    "resolve_project_base_url": "app.core.learning.macro.runner",
    "is_navigation_macro": "app.core.learning.macro.runner",
    "get_navigation_info": "app.core.learning.macro.runner",
    "vault_fill_params": "app.core.learning.macro.runner",
    "invalidate_macro_cache": "app.core.learning.macro.runner",
    "VOICE_POLICY": "app.core.learning.constants",
    "WEB_POLICY": "app.core.learning.constants",
    "ExecutionOutcome": "app.core.learning.macro.runner",
    "MacroGateError": "app.core.learning.macro.runner",
    # 生命周期
    "list_macros": "app.core.learning.macro.lifecycle",
    "load_macro": "app.core.learning.macro.lifecycle",
    "load_verified_macro": "app.core.learning.macro.lifecycle",
    "find_macro_by_name": "app.core.learning.macro.lifecycle",
    "list_active_macro_index": "app.core.learning.macro.lifecycle",
    "create_macro_from_synthesis": "app.core.learning.macro.lifecycle",
    "persist_native_macros": "app.core.learning.macro.lifecycle",
    "confirm_macro": "app.core.learning.macro.lifecycle",
    "confirm_bulk": "app.core.learning.macro.lifecycle",
    "update_macro": "app.core.learning.macro.lifecycle",
    "delete_macro": "app.core.learning.macro.lifecycle",
    "purge_obsolete_macros": "app.core.learning.macro.lifecycle",
    "downgrade_macro": "app.core.learning.macro.lifecycle",
    "mark_obsolete_by_app_map": "app.core.learning.macro.lifecycle",
    "obsolete_macro": "app.core.learning.macro.lifecycle",
    "macro_to_yaml": "app.core.learning.macro.lifecycle",
    # 编译 / 创建 / 迁移
    "MacroScriptCompiler": "app.core.learning.macro.compiler",
    "MacroCreatorService": "app.core.learning.macro.creator",
    # 任务 / 工具
    "native_macro_maintenance": "app.core.learning.macro.maintenance",
    "resurvey_and_regen": "app.core.learning.macro.maintenance",
    "verify_safe_native_macros": "app.core.learning.macro.maintenance",
    "configured_apps": "app.core.learning.macro.maintenance",
    "verify_macro_script": "app.core.learning.macro.utils",
    "cleanup_macro_steps": "app.core.learning.macro.utils",
    # 服务 / 创作门禁
    "MacroService": "app.core.learning.macro.service",
    "validate_script": "app.core.learning.macro.authoring",
    "validate_macro_structure": "app.core.learning.macro.authoring",
    "extract_navigation_url": "app.core.learning.macro.runner",
    # 事件 / 模型
    "MacroMutatedEvent": "app.core.learning.macro.event.schemas",
    "MacroScript": "app.core.learning.macro.schemas",
    "MacroStep": "app.core.learning.macro.schemas",
    "MacroRunResult": "app.core.learning.macro.schemas",
    "MacroVerificationResult": "app.core.learning.macro.schemas",
    "MacroSource": "app.core.learning.macro.schemas",
    "MacroStepType": "app.core.learning.macro.schemas",
}


def __getattr__(name: str):
    module_path = _SYMBOL_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
