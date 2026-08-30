"""hitl → engine 的依赖倒置缝（EngineRuntime）。

hitl 编排层（core / orchestrator）只依赖本模块定义的运行时抽象，不再直接
import 任何 ``app.core.engine.*``；agent 引擎在 ``app.core.engine.hitl_runtime``
中提供实现并自注册。

这是 hitl 包对 engine 的**唯一装配边**，其余模块不得再反向引用 engine。
装配采用与 ``app.core.engine.message`` 相同的惰性策略（importlib 延迟加载，
避免 import 期拉起重型依赖），首次 ``get_runtime`` 时完成注册、幂等且加锁。
"""

import importlib
import logging
import threading
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EngineRuntime(Protocol):
    """HITL 编排层需要的 agent 引擎运行能力（最小面）。"""

    def push_hitl_request(
        self,
        *,
        thread_id: str,
        project_id: int | None,
        run_id: str | None,
        request_type: str,
        prompt: str,
        request_id: str,
        options: list[str] | None,
        context: str | None,
        default_value: str | None,
        tool_call_id: str | None,
        tool_name: str,
        parent_id: str | None,
        metadata: dict | None,
    ) -> None:
        """将 HITL 请求推送到当前会话渠道（异步执行，不等待）。

        实现需自行完成 subagent 通道判断（``ContextManager``）。
        """
        ...

    async def close_hitl_message(
        self, thread_id: str, tool_call_id: str, status: str
    ) -> bool:
        """按 tool_call_id 关闭 HITL 请求消息；找到并更新返回 True。"""
        ...

    async def persist_hitl_user_message(
        self,
        thread_id: str,
        project_id: int | None,
        member_id: int,
        tool_call_id: str,
        user_content: str | None,
        final_result: str,
    ) -> None:
        """把 HITL 用户答复落为 human 消息并更新原 tool 消息结果。"""
        ...

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: dict,
        tool_call_id: str,
        config: dict,
        state: Any = None,
    ) -> str:
        """按原始参数重执行授权门控工具，返回结果文本。"""
        ...


_runtime: EngineRuntime | None = None
# RLock：get_runtime 持锁惰性装配时，模块副作用 register() 会重入加锁。
_runtime_lock = threading.RLock()


def register_engine_runtime(runtime: EngineRuntime) -> None:
    """注入引擎实现（engine 侧自注册 / 测试注入 fake）。"""
    global _runtime
    with _runtime_lock:
        _runtime = runtime


def reset_engine_runtime() -> None:
    """清除已注册引擎实现，主要用于测试隔离。"""
    global _runtime
    with _runtime_lock:
        _runtime = None


def get_runtime() -> EngineRuntime:
    """返回已注册的引擎实现；未注册时惰性装配一次并缓存。

    装配通过 ``importlib.import_module`` 触发 ``app.core.engine.hitl_runtime``
    的 ``register()``——与 ``engine/message/__init__.py`` 的惰性导出同一策略，
    避免在 import 期拉起重型依赖。模块已缓存（如测试 reset 后）时，模块级
    副作用不会重跑，因此在此显式重放 ``register()`` 保证幂等。仅当引擎实现
    模块缺失或未注册时才抛错（Fail-Fast，便于测试直接注入 fake）。
    """
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                mod = importlib.import_module("app.core.engine.hitl_runtime")
                register = getattr(mod, "register", None)
                if callable(register):
                    register()
    if _runtime is None:
        raise RuntimeError(
            "EngineRuntime not registered: import app.core.engine.hitl_runtime "
            "or inject via register_engine_runtime() (e.g. pytest fixture)."
        )
    return _runtime
