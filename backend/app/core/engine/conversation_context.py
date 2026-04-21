"""
Conversation Context — Helper for multi-turn conversation context extraction.
"""

from langchain_core.messages import AIMessage, HumanMessage


class ConversationContext:
    """
    Manages conversation context for multi-turn dialogue support.
    Extracts and formats relevant history for Worker prompts.
    """

    @staticmethod
    def extract_relevant_history(
        messages: list,
        current_topic: str,
        max_turns: int = 5
    ) -> str:
        """
        Extract relevant conversation history for context.

        Args:
            messages: Full message history
            current_topic: Current task topic for relevance filtering
            max_turns: Maximum number of recent turns to include

        Returns:
            Formatted context string
        """
        # Get recent human-ai exchanges
        recent_exchanges = []
        turns = 0

        for msg in reversed(messages):
            if turns >= max_turns:
                break

            if isinstance(msg, HumanMessage):
                content = str(msg.content)[:200]  # Truncate long messages
                recent_exchanges.insert(0, f"User: {content}")
                turns += 1
            elif isinstance(msg, AIMessage) and msg.content:
                content = str(msg.content)[:200]
                recent_exchanges.insert(0, f"Assistant: {content}")

        if not recent_exchanges:
            return ""

        return "\n".join(recent_exchanges)

    @staticmethod
    def build_context_aware_mission(
        mission_msg: str,
        conversation_history: str,
        referenced_files: list[str] | None = None
    ) -> str:
        """
        Build mission message with conversation context.

        Args:
            mission_msg: Base mission message
            conversation_history: Formatted conversation history
            referenced_files: Files mentioned in previous turns

        Returns:
            Enhanced mission message with context
        """
        parts = [mission_msg]

        if conversation_history:
            parts.append("\n\n### Conversation Context\n")
            parts.append("Previous exchanges for reference:")
            parts.append(conversation_history)

        if referenced_files:
            parts.append("\n### Referenced Files\n")
            parts.append("Files mentioned in conversation: " + ", ".join(referenced_files))

        return "\n".join(parts)
