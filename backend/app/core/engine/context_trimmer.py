"""
ContextTrimmer - Unified message trimming for EvoLoop.

Single entry point for all message trimming operations.
Token-driven, model-aware, node-aware.

Design principles:
1. ONE unit: Token (estimated as chars / 4)
2. ONE class: ContextTrimmer handles everything
3. ONE repair: delegates to EvoMessageConverter.repair() — no private copy
4. Token budget driven: no fixed message counts
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.engine.message.converter import EvoMessageConverter
from app.core.engine.message.forgetting import apply_forgotten_status
from app.core.engine.message.utils import count_total_tokens, estimate_message_tokens
from app.core.engine.message.utils import get_message_text
from app.core.memory.tool_output_memory import ToolOutputMemory
from app.infrastructure.llm.platform_service import llm_platform_service

logger = logging.getLogger(__name__)

# Node budget ratios: fraction of model context window allocated per node type
NODE_BUDGET_RATIOS: dict[str, float] = {
    "supervisor": 0.25,   # Routing decisions need less history
    "worker": 0.60,       # Execution needs more context for long-horizon tasks
    "finish": 0.75,       # Summary needs maximum history
    "chat": 0.55,         # Conversation needs more turns
    "default": 0.40,
}

# Trigger trimming when token usage exceeds this fraction of budget
TRIM_THRESHOLD_RATIO = 0.70

# Hard limit: never exceed this fraction of model context (reserve for output)
HARD_LIMIT_RATIO = 0.90

# Layer proportions within effective budget
LAYER_RECENT_RATIO = 0.50   # Layer 1: full retention
LAYER_MIDDLE_RATIO = 0.40   # Layer 2: selective retention
LAYER_EARLY_RATIO = 0.10    # Layer 3: topic marker

# Retry cleanup config
MAX_RETRY_ERRORS = 3


class TrimTrigger(Enum):
    NONE = auto()
    TOKEN_BUDGET = auto()
    MODEL_LIMIT = auto()
    RETRY_CLEANUP = auto()


@dataclass(frozen=True)
class TrimResult:
    messages: list[BaseMessage]
    trigger: TrimTrigger
    before_tokens: int
    after_tokens: int
    before_count: int
    after_count: int
    removed_count: int
    stage_log: list[dict] = field(default_factory=list)


def _compute_budget(model: str, node_source: str) -> tuple[int, int]:
    """
    Compute token budget for a node.

    Returns:
        (effective_budget, hard_limit) in tokens
    """
    profile = llm_platform_service.get_profile(model)
    model_max = profile.max_context_tokens or DEFAULT_MAX_CONTEXT_TOKENS
    node_ratio = NODE_BUDGET_RATIOS.get(node_source, NODE_BUDGET_RATIOS["default"])
    effective_budget = int(model_max * node_ratio)
    hard_limit = int(model_max * HARD_LIMIT_RATIO)
    return min(effective_budget, hard_limit), hard_limit


class ContextTrimmer:
    """
    Unified message trimming entry point.

    All message trimming in the system goes through this class.
    """

    def trim(
        self,
        messages: list[BaseMessage],
        *,
        model: str,
        node_source: Literal["supervisor", "worker", "finish", "chat", "aggregator", "default"] = "default",
        tool_memory: ToolOutputMemory | None = None,
        is_retry: bool = False,
        stages: set[Literal["forget", "window", "repair"]] | None = None,
    ) -> TrimResult:
        """
        Unified trim entry.

        Pipeline: retry_cleanup (optional) → forget (optional) → window → repair

        Args:
            messages: Raw message list
            model: Model name (for profile lookup)
            node_source: Node type (determines budget ratio)
            tool_memory: If provided, applies forgetting stage
            is_retry: If True, applies retry cleanup stage
            stages: Optional subset of stages to run. Default: all.

        Returns:
            TrimResult with trimmed messages and metadata
        """
        if stages is None:
            stages = {"forget", "window", "repair"}

        working = list(messages)
        before_count = len(working)
        before_tokens = count_total_tokens(working)
        stage_log: list[dict] = []
        trigger = TrimTrigger.NONE

        # --- Stage 0: Prune trailing errors (unconditional, cheap) ---
        # Remove trailing AIMessages marked as errors to prevent error pollution
        # in the next turn. This is always safe regardless of retry state.
        pruned_errors = 0
        while working and isinstance(working[-1], AIMessage):
            metadata = working[-1].additional_kwargs
            if isinstance(metadata, dict) and metadata.get("is_error") is True:
                working.pop()
                pruned_errors += 1
            else:
                break
        if pruned_errors:
            stage_log.append({"stage": "prune_trailing_errors", "removed": pruned_errors})

        # --- Stage 1: Quick exit if under threshold and not retry ---
        effective_budget, hard_limit = _compute_budget(model, node_source)
        if before_tokens <= int(effective_budget * TRIM_THRESHOLD_RATIO) and not is_retry:
            # Still run repair if requested (cheap and ensures validity)
            if "repair" in stages:
                working = _repair_message_history(working)
            after_tokens = count_total_tokens(working)
            after_count = len(working)
            return TrimResult(
                messages=working,
                trigger=TrimTrigger.NONE,
                before_tokens=before_tokens,
                after_tokens=after_tokens,
                before_count=before_count,
                after_count=after_count,
                removed_count=before_count - after_count,
                stage_log=[{"stage": "pre_check", "action": "short_circuit", "reason": "under_threshold"}],
            )

        # --- Stage 1: Retry cleanup ---
        if is_retry and "forget" in stages:
            working = self._retry_cleanup(working)
            stage_log.append({
                "stage": "retry_cleanup",
                "before": before_count,
                "after": len(working),
            })
            if len(working) < before_count:
                trigger = TrimTrigger.RETRY_CLEANUP

        # --- Stage 2: Forgetting ---
        if tool_memory is not None and "forget" in stages:
            count_before = len(working)
            working = apply_forgotten_status(working, tool_memory)
            stage_log.append({
                "stage": "forgetting",
                "before": count_before,
                "after": len(working),
                "forgotten_count": len(tool_memory.forgotten),
            })

        # --- Stage 3: Token-driven windowing ---
        if "window" in stages:
            count_before = len(working)
            tokens_before = count_total_tokens(working)
            working = self._token_driven_window(working, model, node_source)
            tokens_after = count_total_tokens(working)
            stage_log.append({
                "stage": "windowing",
                "before_count": count_before,
                "after_count": len(working),
                "before_tokens": tokens_before,
                "after_tokens": tokens_after,
            })
            if len(working) < count_before or tokens_after < tokens_before:
                if trigger == TrimTrigger.NONE:
                    trigger = TrimTrigger.TOKEN_BUDGET

        # --- Stage 4: Repair ---
        if "repair" in stages:
            count_before = len(working)
            working = _repair_message_history(working)
            stage_log.append({
                "stage": "repair",
                "before": count_before,
                "after": len(working),
            })

        after_tokens = count_total_tokens(working)
        after_count = len(working)

        # Log structured trim event
        logger.info(
            "context_trimmed",
            extra={
                "node_source": node_source,
                "trigger": trigger.name,
                "model": model,
                "model_max_tokens": get_profile(model).max_context_tokens,
                "token_budget": effective_budget,
                "hard_limit": hard_limit,
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
                "before_count": before_count,
                "after_count": after_count,
                "stages": sorted(stages),
                "is_retry": is_retry,
            },
        )

        return TrimResult(
            messages=working,
            trigger=trigger,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            before_count=before_count,
            after_count=after_count,
            removed_count=before_count - after_count,
            stage_log=stage_log,
        )

    def _retry_cleanup(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """
        Cleanup for retry scenarios:
        1. Keep only last MAX_RETRY_ERRORS error messages
        2. Deduplicate consecutive HumanMessages (skip context_ticket)
        """
        if not messages:
            return messages

        # Split error vs non-error
        error_messages: list[BaseMessage] = []
        non_error_messages: list[BaseMessage] = []

        for msg in messages:
            is_error = False
            if isinstance(msg, AIMessage):
                if msg.additional_kwargs.get("is_error"):
                    is_error = True
                elif isinstance(msg.content, str) and msg.content.startswith("Error:"):
                    is_error = True

            if is_error:
                error_messages.append(msg)
            else:
                non_error_messages.append(msg)

        # Keep only last N errors
        if len(error_messages) > MAX_RETRY_ERRORS:
            removed = len(error_messages) - MAX_RETRY_ERRORS
            logger.info(f"[RetryCleanup] Removing {removed} accumulated error messages (keeping last {MAX_RETRY_ERRORS})")
            error_messages = error_messages[-MAX_RETRY_ERRORS:]

        # Deduplicate HumanMessages
        last_human_idx = -1
        for idx, msg in enumerate(non_error_messages):
            if isinstance(msg, HumanMessage) and msg.name != "context_ticket":
                last_human_idx = idx

        if last_human_idx >= 0:
            segment = non_error_messages[: last_human_idx + 1]
            deduped: list[BaseMessage] = []
            for msg in segment:
                if isinstance(msg, HumanMessage) and msg.name == "context_ticket":
                    deduped.append(msg)
                    continue
                if isinstance(msg, HumanMessage) and deduped:
                    prev = deduped[-1]
                    if isinstance(prev, HumanMessage) and prev.name != "context_ticket":
                        prev_text = get_message_text(prev)
                        curr_text = get_message_text(msg)
                        if prev_text and curr_text and (prev_text in curr_text or curr_text in prev_text):
                            deduped[-1] = msg
                            continue
                deduped.append(msg)
            non_error_messages = deduped + non_error_messages[last_human_idx + 1 :]

        result = non_error_messages + error_messages
        if len(result) < len(messages):
            logger.info(f"[RetryCleanup] {len(messages)} -> {len(result)} messages")
        return result

    def _token_driven_window(
        self,
        messages: list[BaseMessage],
        model: str,
        node_source: str,
    ) -> list[BaseMessage]:
        """
        Token-driven hierarchical slicing.

        Three layers:
        - Layer 1 (Recent): Full retention, ~50% of budget
        - Layer 2 (Middle): Selective retention, ~40% of budget
        - Layer 3 (Early): Topic marker only, ~10% of budget
        """
        if not messages:
            return messages

        effective_budget, hard_limit = _compute_budget(model, node_source)

        # If already within budget, no need to slice
        current_tokens = count_total_tokens(messages)
        if current_tokens <= effective_budget:
            return messages

        logger.info(
            f"[TokenWindow] {node_source}: {len(messages)} msgs, {current_tokens} tokens "
            f"(budget={effective_budget}, hard={hard_limit})"
        )

        result: list[BaseMessage] = []

        # === Layer 1: Recent — full retention from tail ===
        recent_budget = int(effective_budget * LAYER_RECENT_RATIO)
        recent_tokens = 0
        recent_count = 0

        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_message_tokens(messages[i])
            if recent_tokens + msg_tokens > recent_budget and recent_count >= 3:
                # Keep at least 3 messages in recent layer
                break
            recent_tokens += msg_tokens
            recent_count += 1

        recent = messages[-recent_count:] if recent_count > 0 else []
        result.extend(recent)

        # === Layer 2: Middle — selective retention ===
        middle_budget = int(effective_budget * LAYER_MIDDLE_RATIO)
        middle_tokens = 0
        recent_idx = len(messages) - recent_count  # exclusive boundary
        middle_idx = recent_idx

        middle_messages: list[BaseMessage] = []

        for i in range(recent_idx - 1, -1, -1):
            msg = messages[i]
            msg_tokens = estimate_message_tokens(msg)
            is_ticket = msg.name == "context_ticket"

            if isinstance(msg, HumanMessage):
                # User instructions are core drivers — keep them
                # context_ticket carries dynamic context (iteration count,
                # telemetry, etc.) and MUST be preserved even if it exceeds
                # budget. It is treated as a high-priority HumanMessage.
                if is_ticket or middle_tokens + msg_tokens <= middle_budget:
                    middle_messages.insert(0, msg)
                    middle_tokens += msg_tokens
                    middle_idx = i
                if not is_ticket and middle_tokens + msg_tokens > middle_budget:
                    break

            elif isinstance(msg, AIMessage) and msg.tool_calls:
                # Decision records — keep them
                if middle_tokens + msg_tokens <= middle_budget:
                    middle_messages.insert(0, msg)
                    middle_tokens += msg_tokens
                    middle_idx = i
                else:
                    break

            elif isinstance(msg, AIMessage):
                # Regular AI response — summarize if long
                content = get_message_text(msg)
                if len(content) > 500:
                    summarized = AIMessage(
                        content=content[:200] + "... [Earlier response]",
                        additional_kwargs={
                            **(msg.additional_kwargs or {}),
                            "is_summarized": True,
                        },
                    )
                    sum_tokens = estimate_message_tokens(summarized)
                    if middle_tokens + sum_tokens <= middle_budget:
                        middle_messages.insert(0, summarized)
                        middle_tokens += sum_tokens
                        middle_idx = i
                else:
                    if middle_tokens + msg_tokens <= middle_budget:
                        middle_messages.insert(0, msg)
                        middle_tokens += msg_tokens
                        middle_idx = i

            elif isinstance(msg, ToolMessage):
                # Tool outputs: keep only if forgotten (has summary)
                if msg.additional_kwargs.get("forgotten"):
                    if middle_tokens + msg_tokens <= middle_budget:
                        middle_messages.insert(0, msg)
                        middle_tokens += msg_tokens
                        middle_idx = i
                # Non-forgotten ToolMessages are dropped in middle layer

            elif isinstance(msg, SystemMessage):
                # System messages in middle: skip (prompt cache handles them)
                pass

            else:
                # Other message types: keep brief ones
                if msg_tokens < 50 and middle_tokens + msg_tokens <= middle_budget:
                    middle_messages.insert(0, msg)
                    middle_tokens += msg_tokens
                    middle_idx = i

        result = middle_messages + result

        # === Layer 3: Early — topic marker ===
        if middle_idx > 0:
            first_human = next(
                (m for m in messages[:middle_idx] if isinstance(m, HumanMessage)),
                None,
            )
            if first_human:
                content = get_message_text(first_human)
                topic_text = content[:100] + ("..." if len(content) > 100 else "")
                topic_marker = HumanMessage(
                    content=f"[对话开始] {topic_text}",
                    additional_kwargs={
                        **(first_human.additional_kwargs or {}),
                        "is_topic_marker": True,
                    },
                )
                result.insert(0, topic_marker)

        # === Overflow: enforce hard limit ===
        total_tokens = count_total_tokens(result)
        if total_tokens > hard_limit:
            logger.warning(
                f"[TokenWindow] Hard limit exceeded ({total_tokens}/{hard_limit}), "
                f"aggressive pruning"
            )
            # Aggressive: drop non-forgotten ToolMessages first
            pruned = [
                m for m in result
                if not (isinstance(m, ToolMessage) and not m.additional_kwargs.get("forgotten"))
            ]
            if count_total_tokens(pruned) <= hard_limit:
                result = pruned
            else:
                # Still over: keep topic marker + context_ticket + recent messages that fit
                preserved: list[BaseMessage] = []
                ticket_to_preserve: list[BaseMessage] = []
                recent_to_keep: list[BaseMessage] = []
                for m in result:
                    if (m.additional_kwargs or {}).get("is_topic_marker"):
                        preserved.append(m)
                    if m.name == "context_ticket":
                        ticket_to_preserve.append(m)

                for m in reversed(result):
                    if (m.additional_kwargs or {}).get("is_topic_marker"):
                        continue
                    if m.name == "context_ticket":
                        continue
                    test = preserved + ticket_to_preserve + recent_to_keep + [m]
                    if count_total_tokens(test) <= int(hard_limit * 0.95):
                        recent_to_keep.insert(0, m)
                    else:
                        break
                result = preserved + ticket_to_preserve + recent_to_keep

        after_tokens = count_total_tokens(result)
        logger.info(
            f"[TokenWindow] {node_source}: {len(messages)} -> {len(result)} msgs, "
            f"{current_tokens} -> {after_tokens} tokens"
        )
        return result

    def truncate_tool_output(self, content: str, model: str) -> str:
        """
        Truncate a single tool output if it exceeds model-specific limit.

        Args:
            content: Tool output content
            model: Model name for profile-aware limit

        Returns:
            Truncated content with footer if exceeded, original otherwise
        """
        if not content:
            return content

        profile = llm_platform_service.get_profile(model)
        limit_tokens = profile.truncate_limit_tokens
        limit_chars = limit_tokens * 4  # chars per token fallback ratio

        if len(content) <= limit_chars:
            return content

        chars = len(content)
        lines = content.count("\n")
        truncated = content[:limit_chars]
        footer = (
            f"\n...\n"
            f"[Output truncated: {lines} lines / {chars} chars total. "
            f"Use specific read/search tools for more.]"
        )
        return truncated + footer


# ---------------------------------------------------------------------------
# Message history repair — thin delegation shim
# The authoritative implementation lives in EvoMessageConverter.repair().
# ---------------------------------------------------------------------------

def _repair_message_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Delegation shim — calls the authoritative EvoMessageConverter.repair().

    All repair logic lives in EvoMessageConverter.repair().  This shim preserves
    backward-compatibility for any internal call-sites inside ContextTrimmer that
    haven't been updated to call EvoMessageConverter directly yet.
    """
    return EvoMessageConverter.repair(messages)
