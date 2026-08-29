"""HITL (Human-in-the-Loop) and authorization framework.

注意：本包**不急切导入** ``core`` / ``orchestrator`` 等子模块——它们依赖
``app.core.hitl.engine_runtime`` 与 ``app.core.hitl.activity_sink`` 两个依赖
倒置缝（运行环境由 engine / monitoring 注入，方向已归位为单向下游依赖，
不再有反向环）。此处仅 re-export 叶子模块 ``types``；需要核心能力时请直接
导入子模块，例如：

    from app.core.hitl.core import create_request, raise_hitl_interrupt
    from app.core.hitl.orchestrator import HITLOrchestrator
"""

from app.core.hitl.types import HumanRequestType

__all__ = ["HumanRequestType"]
