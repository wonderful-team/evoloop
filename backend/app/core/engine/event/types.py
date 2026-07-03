"""
Agent Engine Event Types
========================

Event type constants for agent execution lifecycle and WebSocket communication.
"""

from enum import Enum


class AgentEventType(str, Enum):
    """
    Agent Execution event types.

    Events related to agent runs and interactions.
    """
    RUN_STARTED = "agent.run_started"
    RUN_COMPLETED = "agent.run_completed"
    RUN_CANCELLED = "agent.run_cancelled"
    TOOL_EXECUTED = "agent.tool_executed"
    HITL_REQUESTED = "agent.hitl_requested"
    HITL_RESPONDED = "agent.hitl_responded"


class ConversationEventType(str, Enum):
    """
    Conversation lifecycle event types.

    Each module subscribes and cleans up its own data.
    """
    CONVERSATION_DELETED = "conversation.deleted"
