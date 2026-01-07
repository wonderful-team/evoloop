from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, DateTime, Text, Boolean, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow

class TraceEvent(Base):
    """
    Represents a high-fidelity snapshot of agent execution for Imitation Learning.
    Stores State -> Action tuples.

    Supports both:
    - Agent actions (LLM/tool calls, automatically captured)
    - Human actions (UI interactions, captured via frontend ActionRecorder)
    """
    __tablename__ = "trace_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    step_number: Mapped[int] = mapped_column(Integer)

    # State Context
    node_name: Mapped[str] = mapped_column(String(100))
    state_snapshot: Mapped[dict] = mapped_column(Text) # Huge JSON of inputs/scratchpad

    # Action
    action_type: Mapped[str] = mapped_column(String(50)) # "node_start", "llm_call", "tool_call", "user_intervention", "user_click", "user_input"
    action_payload: Mapped[dict] = mapped_column(Text) # JSON of args/output/message

    # Human/Agent Distinction (Phase 1)
    is_human_action: Mapped[bool] = mapped_column(default=False) # True if action was performed by human, not agent

    # Visual Context (Phase 1)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True) # Path to screenshot taken at this moment
    ui_element_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # JSON: target element selector, text, bounds

    # Feedback & Reward
    reward: Mapped[Optional[float]] = mapped_column(Integer, nullable=True) # Normalized reward if available
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # User correction/comment

    # Session Tracking
    recording_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True) # Groups events in one recording session
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # New columns for compatibility with new refactors (Nullable)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    timestamp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class LearnedSkill(Base):
    """
    Stores learned skills synthesized from trace sequences.
    These can be matched to user intents and executed automatically.
    """
    __tablename__ = "learned_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)

    # Matching
    trigger_patterns: Mapped[str] = mapped_column(Text)  # JSON list of trigger patterns

    # Configuration
    parameters: Mapped[str] = mapped_column(Text)  # JSON list of SkillParameter
    preconditions: Mapped[str] = mapped_column(Text, nullable=True)  # JSON list of preconditions
    steps: Mapped[str] = mapped_column(Text)  # JSON list of SkillStep
    tools_used: Mapped[str] = mapped_column(Text, nullable=True)  # JSON list of tool names

    # Source Reference
    source_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Usage Statistics
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    
    # New fields compatibility
    project_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(1536), nullable=True)
