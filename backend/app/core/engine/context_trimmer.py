"""
ContextTrimmer - Unified message trimming for EvoLoop (native BaseMessage version).
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Literal

from app.constants import DEFAULT_MAX_CONTEXT_TOKENS
from app.core.engine.message.converter import EvoMessageConverter
from app.core.engine.message.forgetting import apply_forgotten_status
from app.core.engine.message.native_classes import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from app.core.engine.message.utils import (
    count_total_tokens,
    estimate_message_tokens,
    get_message_text,
)
from app.core.memory.tool_output_memory import ToolOutputMemory
from app.infrastructure.llm.platform_service import llm_platform_service

logger = logging.getLogger(__name__)

NODE_BUDGET_RATIOS: dict[str, float] = {
    "supervisor": 0.30,
    "worker": 0.85,
    "finish": 0.80,
    "chat": 0.80,
    "default": 0.60,
}

TRIM_THRESHOLD_RATIO = 0.70
HARD_LIMIT_RATIO = 0.95

LAYER_RECENT_RATIO = 0.50
LAYER_MIDDLE_RATIO = 0.40
LAYER_EARLY_RATIO = 0.10

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
    profile = llm_platform_service.get_profile(model)
    model_max = profile.max_context_tokens or DEFAULT_MAX_CONTEXT_TOKENS
    node_ratio = NODE_BUDGET_RATIOS.get(node_source, NODE_BUDGET_RATIOS["default"])
    effective_budget = int(model_max * node_ratio)
    hard_limit = int(model_max * HARD_LIMIT_RATIO)
    return min(effective_budget, hard_limit), hard_limit


class ContextTrimmer:
    """
    Unified message trimming entry point using native BaseMessage objects.
    """

    def trim(
        self,
        messages: list[Any],
        *,
        model: str | None = None,
        node_source: Literal["supervisor", "worker", "finish", "aggregator", "default"] = "default",
        tool_memory: ToolOutputMemory | None = None,
        is_retry: bool = False,
        stages: set[Literal["forget", "window", "repair"]] | None = None,
    ) -> TrimResult:
        if stages is None:
            stages = {"forget", "window", "repair"}

        working = list(messages)
        before_count = len(working)
        before_tokens = count_total_tokens(working)
        stage_log: list[dict] = []
        trigger = TrimTrigger.NONE

        # --- Stage 0: Prune trailing errors ---
        pruned_errors = 0
        while working and working[-1].role == "assistant":
            metadata = working[-1].additional_kwargs or {}
            if metadata.get("is_error") is True:
                working.pop()
                pruned_errors += 1
            else:
                break
        if pruned_errors:
            stage_log.append({"stage": "prune_trailing_errors", "removed": pruned_errors})

        # --- Stage 1: Quick exit ---
        effective_budget, hard_limit = _compute_budget(model or "", node_source)
        if before_tokens <= int(effective_budget * TRIM_THRESHOLD_RATIO) and not is_retry:
            if "repair" in stages:
                working = EvoMessageConverter.repair(working)
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
            try:
                working = apply_forgotten_status(working, tool_memory)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                logger.warning(f"[ContextTrimmer] apply_forgotten_status failed: {e}")
            stage_log.append({
                "stage": "forgetting",
                "before": count_before,
                "after": len(working),
                "forgotten_count": len(tool_memory.forgotten) if hasattr(tool_memory, "forgotten") else 0,
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
            working = EvoMessageConverter.repair(working)
            stage_log.append({
                "stage": "repair",
                "before": count_before,
                "after": len(working),
            })

        after_tokens = count_total_tokens(working)
        after_count = len(working)

        logger.info(
            f"[ContextTrimmer] Finished: {node_source} | trigger={trigger.name} | "
            f"tokens={before_tokens} -> {after_tokens} | messages={before_count} -> {after_count}"
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
        if not messages:
            return messages

        error_messages: list[BaseMessage] = []
        non_error_messages: list[BaseMessage] = []

        for msg in messages:
            is_error = False
            if msg.role == "assistant":
                if msg.additional_kwargs.get("is_error"):
                    is_error = True
                elif isinstance(msg.content, str) and msg.content.startswith("Error:"):
                    is_error = True

            if is_error:
                error_messages.append(msg)
            else:
                non_error_messages.append(msg)

        if len(error_messages) > MAX_RETRY_ERRORS:
            error_messages = error_messages[-MAX_RETRY_ERRORS:]

        last_human_idx = -1
        for idx, msg in enumerate(non_error_messages):
            if msg.role == "user" and msg.name != "context_ticket":
                last_human_idx = idx

        if last_human_idx >= 0:
            segment = non_error_messages[: last_human_idx + 1]
            deduped: list[BaseMessage] = []
            for msg in segment:
                if msg.role == "user" and msg.name == "context_ticket":
                    deduped.append(msg)
                    continue
                if msg.role == "user" and deduped:
                    prev = deduped[-1]
                    if prev.role == "user" and prev.name != "context_ticket":
                        prev_text = get_message_text(prev)
                        curr_text = get_message_text(msg)
                        if prev_text and curr_text and (prev_text in curr_text or curr_text in prev_text):
                            deduped[-1] = msg
                            continue
                deduped.append(msg)
            non_error_messages = deduped + non_error_messages[last_human_idx + 1 :]

        return non_error_messages + error_messages

    def _token_driven_window(
        self,
        messages: list[BaseMessage],
        model: str,
        node_source: str,
    ) -> list[BaseMessage]:
        if not messages:
            return messages

        effective_budget, hard_limit = _compute_budget(model or "", node_source)
        current_tokens = count_total_tokens(messages)
        if current_tokens <= effective_budget:
            return messages

        result: list[BaseMessage] = []

        # Layer 1: Recent (full retention)
        recent_budget = int(effective_budget * LAYER_RECENT_RATIO)
        recent_tokens = 0
        recent_count = 0

        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_message_tokens(messages[i])
            if recent_tokens + msg_tokens > recent_budget and recent_count >= 3:
                break
            recent_tokens += msg_tokens
            recent_count += 1

        recent = messages[-recent_count:] if recent_count > 0 else []
        result.extend(recent)

        # Layer 2: Middle
        middle_budget = int(effective_budget * LAYER_MIDDLE_RATIO)
        middle_tokens = 0
        recent_idx = len(messages) - recent_count
        middle_idx = recent_idx

        middle_messages: list[BaseMessage] = []

        for i in range(recent_idx - 1, -1, -1):
            msg = messages[i]
            msg_tokens = estimate_message_tokens(msg)
            role = msg.role
            content = msg.content
            is_ticket = msg.name == "context_ticket"

            if role == "user":
                if is_ticket or middle_tokens + msg_tokens <= middle_budget:
                    middle_messages.insert(0, msg)
                    middle_tokens += msg_tokens
                    middle_idx = i
                if not is_ticket and middle_tokens + msg_tokens > middle_budget:
                    break
            elif role == "assistant" and msg.tool_calls:
                if middle_tokens + msg_tokens <= middle_budget:
                    middle_messages.insert(0, msg)
                    middle_tokens += msg_tokens
                    middle_idx = i
                else:
                    break
            elif role == "assistant":
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
            elif role == "tool":
                add_kw = msg.additional_kwargs or {}
                if add_kw.get("forgotten"):
                    if middle_tokens + msg_tokens <= middle_budget:
                        middle_messages.insert(0, msg)
                        middle_tokens += msg_tokens
                        middle_idx = i
                else:
                    placeholder = ToolMessage(
                        content="[TRIMMED: Tool output removed due to context window limits.]",
                        tool_call_id=msg.tool_call_id or "unknown_id",
                        name=msg.name or "unknown_tool",
                        additional_kwargs={"is_summarized": True},
                    )
                    ph_tokens = estimate_message_tokens(placeholder)
                    if middle_tokens + ph_tokens <= middle_budget:
                        middle_messages.insert(0, placeholder)
                        middle_tokens += ph_tokens
                        middle_idx = i
            elif role == "system":
                pass
            else:
                if msg_tokens < 50 and middle_tokens + msg_tokens <= middle_budget:
                    middle_messages.insert(0, msg)
                    middle_tokens += msg_tokens
                    middle_idx = i

        result = middle_messages + result

        # Layer 3: Topic marker
        if middle_idx > 0:
            first_human = next(
                (m for m in messages[:middle_idx] if m.role == "user"),
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

        # Enforce hard limit
        total_tokens = count_total_tokens(result)
        if total_tokens > hard_limit:
            pruned: list[BaseMessage] = []
            for m in result:
                if m.role == "tool" and not (m.additional_kwargs or {}).get("forgotten"):
                    pruned.append(ToolMessage(
                        content="[TRIMMED: Tool output removed due to context limit.]",
                        tool_call_id=m.tool_call_id or "unknown_id",
                        name=m.name or "unknown_tool",
                        additional_kwargs={"is_summarized": True},
                    ))
                else:
                    pruned.append(m)
            if count_total_tokens(pruned) <= hard_limit:
                result = pruned
            else:
                preserved: list[BaseMessage] = []
                ticket_to_preserve: list[BaseMessage] = []
                recent_to_keep: list[BaseMessage] = []
                for m in result:
                    add_kw = m.additional_kwargs or {}
                    if add_kw.get("is_topic_marker"):
                        preserved.append(m)
                    if m.name == "context_ticket":
                        ticket_to_preserve.append(m)

                for m in reversed(result):
                    add_kw = m.additional_kwargs or {}
                    if add_kw.get("is_topic_marker") or m.name == "context_ticket":
                        continue
                    test = preserved + ticket_to_preserve + recent_to_keep + [m]
                    if count_total_tokens(test) <= int(hard_limit * 0.95):
                        recent_to_keep.insert(0, m)
                    else:
                        break
                result = preserved + ticket_to_preserve + recent_to_keep

        return result
