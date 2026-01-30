"""Pruning strategy for managing conversation context."""

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from app.i18n.service import i18n


class SmartPruningStrategy:
    """
    Implements 'Smart Pruning' strategy from OpenCode.
    - Monitors total token count (heuristic).
    - If limit exceeded, prunes old tool outputs.
    - Preserves recent context (last N turns).
    """

    # Constants
    PRUNE_PROTECT_TOKENS = 30000  # Start pruning if history > 30k chars (~7k tokens)
    MIN_TURNS_TO_KEEP = 2  # Keep last 2 user/assistant turns intact

    @staticmethod
    def prune_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
        """
        Prunes old tool messages if context is too large.
        Returns the modified list of messages.
        """
        if not messages:
            return messages

        # Heuristic: Check total length (faster than tokenizer)
        total_chars = sum(len(m.content) for m in messages)

        # If we are safe, just return
        if total_chars < SmartPruningStrategy.PRUNE_PROTECT_TOKENS:
            return messages

        # Identify protected range (last N turns)
        turns = 0
        protected_index = 0

        # Iterate backwards to find cut-off
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage):
                turns += 1
            if turns >= SmartPruningStrategy.MIN_TURNS_TO_KEEP:
                protected_index = i
                break

        # Pruning Pass: Only prune messages BEFORE the protected index
        pruned_messages = []
        for i, msg in enumerate(messages):
            if i < protected_index and isinstance(msg, ToolMessage):
                # Check if it's already pruned?
                if str(msg.content) == "[Pruned Tool Output]":
                    pruned_messages.append(msg)
                    continue

                # Prune it!
                pruned_msg = ToolMessage(
                    content=i18n.get("prompts.memory.pruned_output"),
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                    additional_kwargs={"original_length": len(str(msg.content))},
                )
                pruned_messages.append(pruned_msg)
            else:
                pruned_messages.append(msg)

        return pruned_messages

    @staticmethod
    def get_token_usage_proxy(messages: list[BaseMessage]) -> int:
        """Estimate token usage using character count."""
        return sum(len(str(m.content)) for m in messages) // 4
