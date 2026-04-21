"""
Hierarchical window slicing for multi-turn conversation support.
"""

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from app.constants import DEFAULT_CONTEXT_LIMIT, DEFAULT_WINDOW_CONFIG, DEFAULT_WINDOW_SIZE
from app.core.engine.message.utils import get_message_text
from app.infrastructure.llm.model_profile import get_profile

logger = logging.getLogger(__name__)


def _get_window_size(model: str | None = None) -> int:
    """Get window size from ModelProfile, falling back to default."""
    try:
        profile = get_profile(model) if model else None
        if profile:
            return profile.window_size
    except ImportError:
        pass
    return DEFAULT_WINDOW_SIZE


def _hierarchical_slice(
    messages: list[BaseMessage],
    effective_window: int,
    max_total_chars: int,
    node_source: str = "default",
) -> list[BaseMessage]:
    """
    Hierarchical message slicing for multi-turn conversation support.
    
    Three-layer approach:
    - Layer 1 (Recent): Full retention - complete messages
    - Layer 2 (Middle): Summary retention - decisions kept, tool outputs collapsed
    - Layer 3 (Early): Topic marker only - first HumanMessage preserved as topic anchor
    
    This preserves conversation continuity without LLM summarization costs.
    
    Args:
        messages: Full message list
        effective_window: Target window size (message count)
        max_total_chars: Character limit
        node_source: Which node is requesting (affects layer proportions)
    
    Returns:
        Hierarchically sliced messages
    """
    config = DEFAULT_WINDOW_CONFIG.get(node_source, DEFAULT_WINDOW_CONFIG["default"])
    full_keep = min(config["full_keep"], effective_window)
    summary_keep = config["summary_keep"]

    result = []

    # === Layer 1: Recent messages - FULL RETENTION ===
    # Always keep the most recent N messages completely intact
    recent_count = min(full_keep, len(messages))
    recent = messages[-recent_count:]
    result.extend(recent)

    remaining_budget = effective_window - recent_count
    if remaining_budget <= 0 or len(messages) <= recent_count:
        return result

    # === Layer 2: Middle section - SUMMARY RETENTION ===
    # Keep HumanMessages and AIMessages with tool_calls, collapse ToolMessages
    middle_start = max(0, len(messages) - recent_count - summary_keep)
    middle_end = len(messages) - recent_count

    middle_messages = []
    for i in range(middle_start, middle_end):
        msg = messages[i]

        if isinstance(msg, ToolMessage):
            # DISABLED: ToolMessage compression removed to avoid triple compression.
            # Agent-controlled forgetting (forget_tool_outputs) now handles this.
            # Keep original ToolMessage in middle section if within budget.
            middle_messages.append(msg)

        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                # Keep AI decision to call tools (important for context)
                middle_messages.append(msg)
            else:
                # Regular AI response - summarize if too long
                content = get_message_text(msg)
                if len(content) > 500:
                    summarized = AIMessage(
                        content=content[:200] + "... [Earlier response]",
                        additional_kwargs={
                            **(msg.additional_kwargs or {}),
                            "is_summarized": True,
                        }
                    )
                    middle_messages.append(summarized)
                else:
                    middle_messages.append(msg)

        elif isinstance(msg, HumanMessage):
            # Keep user inputs (they're the conversation drivers)
            middle_messages.append(msg)

        else:
            # System messages in middle section - keep brief ones only
            content = get_message_text(msg)
            if len(content) < 200:
                middle_messages.append(msg)

    # Add middle messages if within budget
    if len(middle_messages) <= remaining_budget:
        result = middle_messages + result
        remaining_budget -= len(middle_messages)
    else:
        # Budget exhausted, only add last portion of middle section
        result = middle_messages[-remaining_budget:] + result
        remaining_budget = 0

    # === Layer 3: Early messages - TOPIC MARKER ONLY ===
    # If we have remaining budget and early messages exist, preserve topic marker
    if remaining_budget > 0 and middle_start > 0:
        first_human = next(
            (m for m in messages[:middle_start] if isinstance(m, HumanMessage)),
            None
        )
        if first_human:
            content = get_message_text(first_human)
            topic_marker = HumanMessage(
                content=f"[对话开始] {content[:100]}{'...' if len(content) > 100 else ''}",
                additional_kwargs={
                    **(first_human.additional_kwargs or {}),
                    "is_topic_marker": True,
                }
            )
            result.insert(0, topic_marker)

    # === Character Budget Enforcement ===
    # If still over char limit, aggressively prune collapsed messages
    total_chars = sum(len(get_message_text(m)) for m in result)
    if total_chars > max_total_chars:
        logger.warning(
            f"[HierarchicalSlice] Char limit exceeded ({total_chars}/{max_total_chars}), "
            f"pruning collapsed messages"
        )
        # Remove collapsed tool messages first (they're re-executable)
        pruned = [
            m for m in result
            if not (isinstance(m, ToolMessage) and m.additional_kwargs.get("is_collapsed"))
        ]
        # If still over limit, keep only recent messages
        if sum(len(get_message_text(m)) for m in pruned) > max_total_chars:
            # First pass: remove all ToolMessages except forgotten (which have summaries)
            without_tools = [
                m for m in pruned
                if not isinstance(m, ToolMessage) or m.additional_kwargs.get("forgotten")
            ]

            if sum(len(get_message_text(m)) for m in without_tools) <= max_total_chars:
                result = without_tools
            else:
                # Second pass: keep topic marker + last N messages that fit
                # Topic marker should ALWAYS be the first message (index 0)
                preserved = [m for m in without_tools if (m.additional_kwargs or {}).get('is_topic_marker', False)]
                
                # Use a separate list for recent messages to ensure correct relative order
                recent_to_keep = []
                for m in reversed(without_tools):
                    if (m.additional_kwargs or {}).get('is_topic_marker', False):
                        continue
                    
                    test_chars = sum(len(get_message_text(x)) for x in preserved + [m] + recent_to_keep)
                    if test_chars <= max_total_chars * 0.9:  # 10% buffer
                        recent_to_keep.insert(0, m)
                    else:
                        break
                
                result = preserved + recent_to_keep
        else:
            result = pruned

    return result


async def smart_window_slice(
    messages: list[BaseMessage],
    window_size: int | None = None,
    max_total_chars: int = DEFAULT_CONTEXT_LIMIT,
    model: str | None = None,
    node_source: str = "default",
    thread_id: str | None = None,
    user_id: str | None = None,
    project_id: int | None = None,
) -> list[BaseMessage]:
    """
    Smart window slice with hierarchical fallback for multi-turn conversations.

    Strategy:
    1. If messages fit in window: return as-is
    2. If slightly over: use hierarchical slicing (zero LLM cost)
    3. Triggers PreCompact hook before any modification

    Args:
        messages: Full message list
        window_size: Target window size
        max_total_chars: Character limit
        model: Model name for profile-aware sizing
        node_source: Node requesting the slice (affects strategy)
        thread_id, user_id, project_id: For PreCompact hook

    Returns:
        Optimized message list
    """
    effective_window = window_size or _get_window_size(model)

    # 1. Check if we need any processing
    if len(messages) <= effective_window:
        # Still check character budget
        total_chars = sum(len(get_message_text(m)) for m in messages)
        if total_chars <= max_total_chars:
            return messages

    # 2. Trigger PreCompact hook BEFORE context is lost
    if len(messages) > effective_window:
        try:
            from app.core.engine.hooks import HookContext, HookEvent, hook_system

            hook_ctx = HookContext(
                thread_id=thread_id or "unknown",
                user_id=user_id,
                project_id=project_id,
                messages=messages,
            )
            # Await to ensure hook completes before context is lost
            await hook_system.trigger(HookEvent.PRE_COMPACT, hook_ctx)
            logger.debug(f"[HierarchicalSlice] PreCompact hook completed for {thread_id}")
        except Exception as e:
            logger.error(f"[HierarchicalSlice] PreCompact hook failed: {type(e).__name__}: {e}", exc_info=True)

    # 3. Use hierarchical slicing (no LLM cost)
    return _hierarchical_slice(
        messages=messages,
        effective_window=effective_window,
        max_total_chars=max_total_chars,
        node_source=node_source,
    )
