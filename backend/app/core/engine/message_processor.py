"""
MessageProcessor - Handles message lifecycle before inference.

Responsible for:
- Applying forgotten status (soft forgetting)
- Hierarchical smart window slicing
- Repairing orphaned / dangling tool messages

Explicitly NOT responsible for:
- LLM invocation
- Signal interception
- Blackboard updates
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage

from app.constants import DEFAULT_CONTEXT_LIMIT, DEFAULT_WINDOW_SIZE, NODE_WINDOW_SIZES
from app.core.engine.message.utils import apply_forgotten_status, repair_message_history, smart_window_slice
from app.core.memory.tool_output_memory import get_tool_memory_from_state

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Prepares message history for LLM consumption."""

    async def process(
        self,
        messages: list[BaseMessage],
        state: Any,
        config: dict,
        node_source: str = "default",
        model: str | None = None,
    ) -> list[BaseMessage]:
        """
        Full message preparation pipeline.

        Args:
            messages: Raw messages from state
            state: AgentState (for tool memory access)
            config: RunnableConfig (for thread_id, user_id, project_id)
            node_source: Which node is requesting (affects window size)
            model: Model name for profile-aware sizing

        Returns:
            Repaired, windowed, and forgotten-status-applied message list
        """
        raw_messages = list(messages)
        logger.info(
            f"[{node_source}] Raw messages: {len(raw_messages)} | "
            f"Types: {[type(m).__name__ for m in raw_messages]}"
        )

        # 1. Apply Agent-Controlled Forgetting
        tool_memory = get_tool_memory_from_state(state)
        messages_with_forgetting = apply_forgotten_status(raw_messages, tool_memory)
        logger.info(f"[{node_source}] After forgetting: {len(messages_with_forgetting)} messages")

        # 2. Hierarchical Smart Windowing
        ctx_config = config.get("configurable", {}) if config else {}
        effective_window = NODE_WINDOW_SIZES.get(node_source, DEFAULT_WINDOW_SIZE)

        windowed_messages = await smart_window_slice(
            messages_with_forgetting,
            window_size=effective_window,
            max_total_chars=DEFAULT_CONTEXT_LIMIT,
            model=model,
            node_source=node_source or "default",
            thread_id=ctx_config.get("thread_id"),
            user_id=ctx_config.get("user_id"),
            project_id=ctx_config.get("project_id"),
        )

        logger.info(
            f"[{node_source}] Window: {len(messages_with_forgetting)} -> {len(windowed_messages)} messages "
            f"(forgotten: {len(tool_memory.forgotten)}, node={node_source}, window={effective_window})"
        )

        # 3. Repair Orphaned Tool Messages
        repaired_messages = repair_message_history(windowed_messages)
        logger.info(
            f"[{node_source}] After repair: {len(repaired_messages)} messages | "
            f"Types: {[type(m).__name__ for m in repaired_messages]}"
        )

        return repaired_messages
