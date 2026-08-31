"""Agent runtime configuration (react engine).

图架构的 ExecutionTicket 已删除。RunnableConfigMetadata 仍被 tool executor /
macro 工具读取执行上下文使用。
"""

from __future__ import annotations

from app.infrastructure.pydantic_base import DynamicBaseModel


class RunnableConfigMetadata(DynamicBaseModel):
    """Metadata extracted from the engine run context."""

    thread_id: str = "unknown"
    member_id: int | None = None
    project_id: int | None = None
    run_id: str | None = None
    model: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> RunnableConfigMetadata:
        """Hydrate metadata from a config dictionary."""
        if not config:
            return cls()

        configurable = config.get("configurable", {}) or {}
        if not configurable:
            configurable = config

        metadata = config.get("metadata", {}) or {}

        project_id = configurable.get("project_id")
        if project_id is None:
            project_id = metadata.get("project_id")

        return cls(
            thread_id=str(configurable.get("thread_id", "unknown")),
            member_id=configurable.get("member_id"),
            project_id=project_id,
            run_id=configurable.get("run_id"),
            model=configurable.get("model"),
        )
