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

    RUN_COMPLETED = "agent.run_completed"


class ConversationEventType(str, Enum):
    """
    Conversation lifecycle event types.

    Each module subscribes and cleans up its own data.
    """

    CONVERSATION_DELETED = "conversation.deleted"
