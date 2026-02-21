"""Pruning strategy for managing conversation context."""

import logging

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class SmartPruningStrategy:
    """
    Implements 'Smart Pruning' strategy (model-aware).
    
    - Dynamically determines pruning threshold based on the current model's context window.
    - Uses precise token counting when available, falls back to character estimation.
    - Preserves recent context (last N turns).
    - Prunes old tool outputs first (they can be re-fetched).
    """

    # Keep last 2 user/assistant turns intact regardless of token count
    MIN_TURNS_TO_KEEP = 2

    @staticmethod
    def prune_messages(
        messages: list[BaseMessage],
        model: str | None = None,
    ) -> list[BaseMessage]:
        """
        Prunes old tool messages if context is too large.
        
        Args:
            messages: The full message list.
            model: Optional model name for profile-aware thresholds.
        
        Returns:
            The modified list of messages.
        """
        if not messages:
            return messages

        # --- Dynamic threshold from ModelProfile ---
        try:
            from app.infrastructure.llm.model_profile import get_current_profile
            from app.utils.token import count_messages_tokens

            profile = get_current_profile(model) if model else None
            if profile:
                total_tokens = count_messages_tokens(messages, model or "gpt-4o")
                threshold = profile.prune_threshold_tokens

                if total_tokens < threshold:
                    return messages

                logger.info(
                    f"Pruning triggered: {total_tokens} tokens > threshold {threshold} "
                    f"(model={profile.name}, context={profile.max_context_tokens})"
                )
            else:
                # Fallback to character heuristic
                total_chars = sum(len(str(m.content)) for m in messages)
                if total_chars < 30000:
                    return messages
        except ImportError:
            # Graceful degradation if new modules not yet available
            total_chars = sum(len(str(m.content)) for m in messages)
            if total_chars < 30000:
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
                # Check if it's already pruned
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
    def get_token_usage(messages: list[BaseMessage], model: str | None = None) -> int:
        """
        Get token usage for messages. Uses precise counting when available.
        """
        try:
            from app.utils.token import count_messages_tokens
            return count_messages_tokens(messages, model or "gpt-4o")
        except ImportError:
            return sum(len(str(m.content)) for m in messages) // 4
