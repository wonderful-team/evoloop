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


class WebSocketEventType(str, Enum):
    """
    WebSocket message events from Gateway.

    Published by EvoCloudWebSocketLink when it receives messages from Gateway.
    Business modules subscribe to these instead of registering callbacks on the link.

    .. deprecated::
        ``NEW_COMMAND`` is deprecated. Use ``websocket.message_received``
        with ``msg_type == "new_command"`` instead.
    """
    NEW_COMMAND = "websocket.new_command"


class ConversationEventType(str, Enum):
    """
    Conversation lifecycle event types.

    Each module subscribes and cleans up its own data.
    """
    CONVERSATION_DELETED = "conversation.deleted"
