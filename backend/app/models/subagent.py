"""SubagentRun — persistent lifecycle record for a parallel subagent execution.

Subagents are transient execution units: they do NOT create a Conversation row,
but their lifecycle (running/completed/failed/cancelled/awaiting_*) and final
result must survive process restarts for crash recovery and aggregation.

Design (docs/subagent-design.md §3.1, §D4):
- ``id`` is globally unique = f"{parent_thread_id}-{subagent_id}"
- queries/updates locate by ``thread_id`` (== sub_tid, same value as ``id``)
- parent/child relationship lives here (``parent_thread_id``), not in Conversation
"""

from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


class SubagentStatus(str, Enum):
    """Lifecycle status of a SubagentRun."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_HUMAN = "awaiting_human"
    AWAITING_A2A = "awaiting_a2a"


class SubagentRun(SQLModel, table=True):
    __tablename__ = "subagent_runs"

    id: str = Field(primary_key=True)  # f"{parent_thread_id}-{subagent_id}"
    parent_thread_id: str = Field(index=True)
    thread_id: str = Field(unique=True, index=True)  # sub_tid, == id

    instruction: str
    role_name: str = "Subagent"
    focus_paths: str | None = None  # JSON list
    acceptance_criteria: str | None = None  # JSON list

    status: SubagentStatus = Field(default=SubagentStatus.RUNNING)
    result: str | None = None
    error: str | None = None
    tools_used: str | None = None  # JSON list of tool names

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
