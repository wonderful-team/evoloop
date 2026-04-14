"""
Context Window Management - Handles context compaction with PreCompact hooks.

This module provides context window management inspired by Claude Code:
- Monitor token usage
- Trigger compaction when threshold reached
- Save state via PreCompact hooks before compression
- Smart retention of important messages

Usage:
    context_manager = ContextWindowManager(max_tokens=150000)
    
    # Check and compact if needed
    messages = await context_manager.check_and_compact(messages, thread_id)
    
    # Or manually trigger compaction
    summary = await context_manager.compact(messages)
"""

import logging
import time

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import Field

from app.core.engine.hooks import HookContext, HookEvent, hook_system
from app.core.engine.state.blackboard import BlackboardState
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class CriticalContext(DynamicBaseModel):
    """Critical context extracted from messages before compaction."""
    decisions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    current_task: str | None = None


class ContextWindowStats(DynamicBaseModel):
    """Context window manager statistics."""
    max_tokens: int
    compact_threshold: float
    preserve_recent: int


class CompactionResult(DynamicBaseModel):
    """Result of context compaction."""
    messages: list[BaseMessage]
    summary: str
    tokens_saved: int
    original_count: int
    compacted_count: int
    checkpoint_id: str | None = None


class TokenEstimator:
    """Estimate token count for messages."""

    # Rough approximation: 4 chars ≈ 1 token for English
    CHARS_PER_TOKEN = 4

    # Overhead per message
    MESSAGE_OVERHEAD = 4

    @classmethod
    def estimate(cls, messages: list[BaseMessage]) -> int:
        """Estimate token count for messages."""
        total = 0
        for msg in messages:
            content = str(msg.content) if hasattr(msg, 'content') else ""
            # Content tokens
            total += len(content) // cls.CHARS_PER_TOKEN
            # Message overhead
            total += cls.MESSAGE_OVERHEAD
        return total

    @classmethod
    def estimate_single(cls, message: BaseMessage) -> int:
        """Estimate tokens for a single message."""
        content = str(message.content) if hasattr(message, 'content') else ""
        return len(content) // cls.CHARS_PER_TOKEN + cls.MESSAGE_OVERHEAD


class ContextSummarizer:
    """Summarize conversation history for compaction."""

    async def summarize(
        self,
        messages: list[BaseMessage],
        preserve_recent: int = 10,
    ) -> str:
        """
        Create a summary of older messages.
        
        Args:
            messages: All messages to summarize
            preserve_recent: Number of recent messages to keep as-is
        
        Returns:
            Summary text to inject as system message
        """
        if len(messages) <= preserve_recent:
            return ""

        # Messages to summarize (older ones)
        to_summarize = messages[:-preserve_recent]

        # Extract key information
        human_inputs = []
        ai_outputs = []
        tool_calls = []

        for msg in to_summarize:
            if isinstance(msg, HumanMessage):
                human_inputs.append(str(msg.content)[:100])
            elif isinstance(msg, AIMessage):
                content = str(msg.content)
                if content:
                    ai_outputs.append(content[:100])
            elif isinstance(msg, ToolMessage):
                tool_calls.append(f"Tool: {msg.name}")

        # Build summary
        summary_parts = ["## Previous Conversation Summary\n"]

        if human_inputs:
            summary_parts.append("### User Requests")
            for i, inp in enumerate(human_inputs[-5:], 1):
                summary_parts.append(f"{i}. {inp}...")
            summary_parts.append("")

        if ai_outputs:
            summary_parts.append("### Key Actions Taken")
            for i, out in enumerate(ai_outputs[-5:], 1):
                # Extract first sentence or first 80 chars
                summary = out.split('.')[0][:80]
                summary_parts.append(f"{i}. {summary}...")
            summary_parts.append("")

        if tool_calls:
            summary_parts.append("### Tools Used")
            unique_tools = list(set(tool_calls))[-5:]
            summary_parts.append(", ".join(unique_tools))
            summary_parts.append("")

        summary = "\n".join(summary_parts)
        return summary

    def extract_critical_context(self, messages: list[BaseMessage]) -> CriticalContext:
        """Extract critical context that must be preserved."""
        critical = CriticalContext()

        for msg in messages:
            content = str(msg.content).lower() if hasattr(msg, 'content') else ""

            # Extract decisions
            if any(kw in content for kw in ['decided', 'decision', 'choose', 'selected']):
                critical.decisions.append(str(msg.content)[:150])

            # Extract errors
            if any(kw in content for kw in ['error', 'failed', 'exception']):
                critical.errors.append(str(msg.content)[:150])

            # Extract file modifications
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get('name') in ['edit_file', 'write_file']:
                        args = tc.get('args', {})
                        if 'file_path' in args:
                            critical.files_modified.append(args['file_path'])

        # Get current task from most recent human message
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                critical.current_task = str(msg.content)[:200]
                break

        return critical


class ContextWindowManager:
    """
    Manage context window with compaction and PreCompact hooks.
    
    This is the core of Claude Code's context management:
    1. Monitor token usage
    2. Trigger PreCompact hook before compression
    3. Save critical state
    4. Compact old messages to summary
    5. Preserve recent messages
    """

    # Default thresholds
    DEFAULT_MAX_TOKENS = 150000  # Leave room for response
    COMPACT_THRESHOLD = 0.8      # Compact at 80% capacity
    PRESERVE_RECENT = 10         # Keep last 10 messages

    def __init__(
        self,
        max_tokens: int | None = None,
        compact_threshold: float | None = None,
    ):
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.compact_threshold = compact_threshold or self.COMPACT_THRESHOLD
        self.token_estimator = TokenEstimator()
        self.summarizer = ContextSummarizer()

        logger.info(
            f"[ContextManager] Initialized: max={self.max_tokens}, "
            f"threshold={self.compact_threshold}"
        )

    async def check_and_compact(
        self,
        messages: list[BaseMessage],
        thread_id: str,
        project_id: int | None = None,
        user_id: str | None = None,
        blackboard: BlackboardState | None = None,
    ) -> list[BaseMessage]:
        """
        Check token count and compact if needed.
        
        This is the main entry point - call this before sending
        messages to the LLM.
        
        Args:
            messages: Current message list
            thread_id: Thread identifier
            project_id: Optional project ID
            user_id: Optional user ID
            blackboard: Optional blackboard state
        
        Returns:
            Original or compacted messages
        """
        token_count = self.token_estimator.estimate(messages)
        threshold_tokens = int(self.max_tokens * self.compact_threshold)

        if token_count < threshold_tokens:
            # No compaction needed
            return messages

        logger.warning(
            f"[ContextManager] Context window at {token_count}/{self.max_tokens} "
            f"({token_count/self.max_tokens*100:.1f}%) - triggering compaction"
        )

        # Trigger compaction
        result = await self.compact(
            messages=messages,
            thread_id=thread_id,
            project_id=project_id,
            user_id=user_id,
            blackboard=blackboard,
        )

        return result.messages

    async def compact(
        self,
        messages: list[BaseMessage],
        thread_id: str,
        project_id: int | None = None,
        user_id: str | None = None,
        blackboard: BlackboardState | None = None,
    ) -> CompactionResult:
        """
        Compact context by summarizing old messages.

        Process:
        1. Trigger PreCompact hook (save state)
        2. Extract critical context
        3. Summarize old messages
        4. Create compacted message list
        5. Return result with metadata
        """
        total_start = time.time()
        original_count = len(messages)
        original_tokens = self.token_estimator.estimate(messages)

        logger.info(f"[ContextManager] 🔄 COMPACT START: {original_count} messages, ~{original_tokens} tokens, thread={thread_id}")

        # Step 1: Trigger PreCompact hook (CRITICAL)
        hook_start = time.time()
        context = HookContext(
            thread_id=thread_id,
            project_id=project_id,
            user_id=user_id,
            messages=messages,
            blackboard=blackboard,
            metadata={
                "token_count": original_tokens,
                "compaction_reason": "threshold_exceeded",
            },
        )

        logger.debug("[ContextManager] Triggering PRE_COMPACT hook...")
        hook_result = await hook_system.trigger(
            HookEvent.PRE_COMPACT,
            context,
        )
        hook_elapsed = (time.time() - hook_start) * 1000

        checkpoint_id = None
        if hook_result.success and hook_result.data:
            checkpoint = hook_result.data.get("checkpoint", {})
            checkpoint_id = hook_result.data.get("checkpoint_id")
            skipped = hook_result.data.get("skipped", False)
            if skipped:
                logger.info(f"[ContextManager] ⏭️ PreCompact hook skipped (duplicate) in {hook_elapsed:.1f}ms")
            else:
                logger.info(f"[ContextManager] ✅ PreCompact checkpoint saved: {checkpoint_id} in {hook_elapsed:.1f}ms")
        else:
            logger.warning(f"[ContextManager] ⚠️ PreCompact hook failed or returned no data in {hook_elapsed:.1f}ms: {hook_result}")

        # Step 2: Extract critical context
        extract_start = time.time()
        critical = self.summarizer.extract_critical_context(messages)
        extract_elapsed = (time.time() - extract_start) * 1000
        logger.debug(f"[ContextManager] Extracted critical context: {len(critical['decisions'])} decisions, {len(critical['files_modified'])} files in {extract_elapsed:.1f}ms")

        # Step 3: Create summary
        summary_start = time.time()
        summary = await self.summarizer.summarize(messages, self.PRESERVE_RECENT)
        summary_elapsed = (time.time() - summary_start) * 1000
        logger.debug(f"[ContextManager] Summary created ({len(summary)} chars) in {summary_elapsed:.1f}ms")

        # Add critical context to summary
        if critical["decisions"]:
            summary += "\n### Key Decisions\n"
            for decision in critical["decisions"][-3:]:
                summary += f"- {decision}\n"

        if critical["current_task"]:
            summary += f"\n### Current Task\n{critical['current_task']}\n"

        # Step 4: Build compacted messages
        build_start = time.time()
        compacted = []

        # Add system summary first
        if summary:
            compacted.append(SystemMessage(content=summary))

        # Preserve recent messages
        recent_messages = messages[-self.PRESERVE_RECENT:]
        compacted.extend(recent_messages)
        build_elapsed = (time.time() - build_start) * 1000
        logger.debug(f"[ContextManager] Built compacted message list: {len(compacted)} messages in {build_elapsed:.1f}ms")

        # Step 5: Calculate savings
        compacted_tokens = self.token_estimator.estimate(compacted)
        tokens_saved = original_tokens - compacted_tokens

        result = CompactionResult(
            messages=compacted,
            summary=summary,
            tokens_saved=tokens_saved,
            original_count=original_count,
            compacted_count=len(compacted),
            checkpoint_id=checkpoint_id,
        )

        total_elapsed = (time.time() - total_start) * 1000
        logger.info(
            f"[ContextManager] ✅ COMPACT COMPLETE: {original_count} -> {len(compacted)} messages, "
            f"saved ~{tokens_saved} tokens, checkpoint={checkpoint_id or 'none'}, total={total_elapsed:.1f}ms"
        )

        # Trigger PostCompact hook
        postcompact_start = time.time()
        await hook_system.trigger(
            HookEvent.POST_COMPACT,
            HookContext(
                thread_id=thread_id,
                messages=compacted,
                metadata={
                    "compaction_result": {
                        "tokens_saved": tokens_saved,
                        "checkpoint_id": checkpoint_id,
                    },
                },
            ),
        )
        postcompact_elapsed = (time.time() - postcompact_start) * 1000
        logger.debug(f"[ContextManager] POST_COMPACT hook triggered in {postcompact_elapsed:.1f}ms")

        return result

    def get_stats(self) -> ContextWindowStats:
        """Get context manager statistics."""
        return ContextWindowStats(
            max_tokens=self.max_tokens,
            compact_threshold=self.compact_threshold,
            preserve_recent=self.PRESERVE_RECENT,
        )


# Global context manager instance
context_manager = ContextWindowManager()


# Convenience functions
async def check_and_compact_context(
    messages: list[BaseMessage],
    thread_id: str,
    **kwargs,
) -> list[BaseMessage]:
    """Convenience function for context compaction."""
    return await context_manager.check_and_compact(messages, thread_id, **kwargs)


def estimate_tokens(messages: list[BaseMessage]) -> int:
    """Convenience function for token estimation."""
    return TokenEstimator.estimate(messages)
