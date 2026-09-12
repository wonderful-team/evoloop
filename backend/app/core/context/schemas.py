"""Schemas for context module."""

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ContextMetadata(DynamicBaseModel):
    """Dynamic metadata attached to an EvoContext."""

    source: str | None = None
    has_android: bool | None = None
    has_macos: bool | None = None
    user_preferences: Any | None = None
    project_concepts: Any | None = None
    active_skills: Any | None = None
    active_macros: Any | None = None
    operation_map: str | None = None
    shared_context: dict[str, Any] = Field(default_factory=dict)
    tool_memory: dict | None = None
    iteration_count: int | None = None
    active_plan_context: str | None = None
    prompt: str | None = None
    blackboard: Any | None = None

    # Memory pipeline — populated by AgentContextHydrator
    # Corresponds to Jinja2 template vars: memory.core_raw / memory.episodic_raw
    core_memory_raw: str | None = None
    episodic_memory_raw: str | None = None

    # L0 intent hint passed from entry points to context hydrator
    intent_hint: Any | None = None

    # 能力包可见性（capability-packages-refactor.md §6-#4）：thread 级叠加集。
    # EvoContext 经 ContextManager.save/load 随 thread 持久（build_ctx 每轮 load
    # 恢复），故 ctx 即 thread 级载体——预选集每轮确定性重算，加载集增量叠加。
    loaded_packages: list[str] = Field(default_factory=list)
    # 页面预选集（每轮由 domain+page 确定性重算，hydrate 写入；不持久依赖）
    preselected_packages: list[str] = Field(default_factory=list)
    # 包面脏标记：skill 激活后置位，inference 循环检测到即重算工具面并
    # rebind（同 run 内立即可用，不必等下一次 delivery）
    packages_dirty: bool = Field(default=False)
