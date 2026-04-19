"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.
"""

import logging
from datetime import datetime
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.constants import (
    DEFAULT_CONTEXT_LIMIT,
    DEFAULT_WINDOW_CONFIG,
    DEFAULT_WINDOW_SIZE,
    MAX_OUTPUT_LENGTH,
)
from app.core.engine.state.history import FoldedMessage, ToolCall, ToolStep
from app.core.memory.tool_output_memory import ToolOutputMemory
from app.i18n.service import i18n
from app.infrastructure.llm.model_profile import get_profile
from app.utils import gen_uuid, render_template

logger = logging.getLogger(__name__)


def _get_truncate_limit(model: str | None = None) -> int:
    """Get truncate limit from ModelProfile, falling back to MAX_OUTPUT_LENGTH."""
    try:
        profile = get_profile(model) if model else None
        if profile:
            return profile.truncate_limit_chars
    except ImportError:
        pass
    return MAX_OUTPUT_LENGTH


def _get_window_size(model: str | None = None) -> int:
    """Get window size from ModelProfile, falling back to default."""
    try:
        profile = get_profile(model) if model else None
        if profile:
            return profile.window_size
    except ImportError:
        pass
    return DEFAULT_WINDOW_SIZE


def truncate_message_content(
    content: str,
    limit: int | None = None,
    model: str | None = None,
) -> str:
    """
    Truncate content if it exceeds the limit, adding a metadata footer.
    
    Args:
        content: The content string to truncate.
        limit: Explicit character limit. If None, derived from ModelProfile or MAX_OUTPUT_LENGTH.
        model: Model name for profile-aware limit derivation.
    """
    effective_limit = limit or _get_truncate_limit(model)

    # Use the utility function with custom footer format
    if not content or len(content) <= effective_limit:
        return content

    chars = len(content)
    lines = content.count("\n")
    truncated = content[:effective_limit]
    footer = f"\n...\n[Output truncated: {lines} lines / {chars} chars total. Use specific read/search tools for more.]"
    return truncated + footer


def get_message_text(message: BaseMessage | str) -> str:
    """
    Robustly extract text content from a message object, handling:
    - Normal string content
    - List of blocks (Multimodal/Anthropic)
    """
    if isinstance(message, str):
        return message

    content = message.content
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        # Join all text blocks
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                # Anthropic style: {"type": "text", "text": "..."}
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
        return "\n".join(text_parts)

    return ""


def get_last_human_message(messages: list) -> str | None:
    """Extract the last human message content from a message list."""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return get_message_text(msg)
    return None


def prune_trailing_errors(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Remove trailing AIMessages that are marked as errors to prevent LLM confusion on retry."""
    while messages and isinstance(messages[-1], AIMessage):
        metadata = getattr(messages[-1], "metadata", {}) or {}
        if metadata.get("is_error"):
            messages.pop()
        else:
            break
    return messages


def repair_message_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Ensure the message history is valid for strict LLM APIs (like Anthropic/GLM).
    1. No orphaned ToolMessages (must have preceding AIMessage with tool_calls).
    2. No dangling ToolCalls (must be followed by ToolMessages).
    3. No consecutive messages of same role (Human->Human, AI->AI).
    4. No empty content allowed.

    Args:
        messages: The message list to repair.
    """
    # Default message templates
    defaults = {
        "orphaned_tool": "[Tool execution context missing]",
        "interrupted_tool_response": "[Tool execution was interrupted]",
        "conversation_continuation": "[Conversation continues]",
    }

    def get_msg(key: str) -> str:
        """Get translated message with fallback to defaults."""
        try:
            result = i18n.get(f"core_utils.{key}", default=defaults[key])
            return result if isinstance(result, str) else defaults[key]
        except Exception:
            return defaults[key]

    # Phase 1: Basic cleanup & Orphaned ToolMessage repair
    stage1 = []
    for msg in messages:
        # Check for empty content
        if not msg.content and not isinstance(msg, ToolMessage | AIMessage):
            # AI/Tool messages can have tool_calls instead of content
            continue

        if isinstance(msg, AIMessage) and not msg.content and not msg.tool_calls:
            continue

        if isinstance(msg, ToolMessage):
            # Orphan Check
            is_orphaned = True
            if stage1:
                last = stage1[-1]
                if isinstance(last, AIMessage) and last.tool_calls:
                    ids = [tc['id'] if isinstance(tc, dict) else tc.id for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                        is_orphaned = False

            if is_orphaned:
                dummy = AIMessage(
                    content=get_msg("orphaned_tool"),
                    tool_calls=[ToolCall(
                        id=msg.tool_call_id,
                        name=msg.name or "unknown_tool",
                        args={}
                    ).model_dump()]
                )
                stage1.append(dummy)

            stage1.append(msg)
            continue

        # Strict Role Alternation (Merge consecutive same-role)
        if stage1:
            last = stage1[-1]
            # Use isinstance for subclass compatibility
            if isinstance(last, type(msg)) and isinstance(msg, HumanMessage | AIMessage):
                # Skip merge if last message has tool_calls to preserve structure
                if isinstance(last, AIMessage) and getattr(last, 'tool_calls', None):
                    stage1.append(msg)
                    continue
                # Merge content — create a NEW message object to avoid mutating
                # the original, which may be a shared reference in LangGraph state.
                new_content = f"{last.content}\n\n{msg.content}"
                merged = last.model_copy(update={"content": new_content})
                stage1[-1] = merged
                continue

        stage1.append(msg)

    # Phase 2: Dangling ToolCall repair (AIMessage with tool_calls must be followed by ToolMessages)
    final_repaired = []
    open_tool_calls = {}  # id -> name

    for i, msg in enumerate(stage1):
        # If we see a Human/AI message but have open tool calls from previous AI message,
        # we MUST close them first (Anthropic requirement).
        if isinstance(msg, HumanMessage | AIMessage) and open_tool_calls:
            for tcid, tname in list(open_tool_calls.items()):
                final_repaired.append(ToolMessage(
                    content=get_msg("interrupted_tool_response"),
                    tool_call_id=tcid,
                    name=tname
                ))
            open_tool_calls = {}

        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                # Still handle dict access for raw LangChain messages, but remove redundant validation
                tcid = tc['id'] if isinstance(tc, dict) else tc.id
                tname = tc['name'] if isinstance(tc, dict) else tc.name
                open_tool_calls[tcid] = tname

        if isinstance(msg, ToolMessage):
            # Clear opened call
            if msg.tool_call_id in open_tool_calls:
                del open_tool_calls[msg.tool_call_id]

        final_repaired.append(msg)

    # Final check for trailing tool calls (history cannot end with AIMessage(tool_calls))
    if open_tool_calls and final_repaired:
        logger.warning("🔧 [Repair] History ends with dangling tool calls. Injecting dummy responses.")
        for tcid, tname in list(open_tool_calls.items()):
            final_repaired.append(ToolMessage(
                content=i18n.get("core_utils.interrupted_tool_response"),
                tool_call_id=tcid,
                name=tname
            ))

    # Phase 4: Start with Human
    non_system_indices = [idx for idx, m in enumerate(final_repaired) if not isinstance(m, SystemMessage)]
    if non_system_indices:
        first_idx = non_system_indices[0]
        if isinstance(final_repaired[first_idx], AIMessage):
            final_repaired.insert(first_idx, HumanMessage(content=get_msg("conversation_continuation")))
    elif not final_repaired:
        final_repaired.append(HumanMessage(content=get_msg("conversation_continuation")))

    return final_repaired


def apply_forgotten_status(messages: list[BaseMessage], tool_memory: ToolOutputMemory) -> list[BaseMessage]:
    """
    Apply forgotten status to messages based on ToolOutputMemory.

    Replaces content of forgotten tool outputs with their summaries.
    This implements "soft forgetting" - we keep the message structure
    but replace the heavy content with a lightweight summary.

    Args:
        messages: Original message list
        tool_memory: ToolOutputMemory with forgotten records

    Returns:
        Messages with forgotten ones replaced by summaries
    """
    if not tool_memory or not tool_memory.forgotten:
        return messages

    result = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and tool_memory.is_forgotten(msg.tool_call_id):
            # Get summary and replace content
            record = tool_memory.get_forgotten_info(msg.tool_call_id)
            if record:
                # Create a summary message that maintains the tool structure
                # but replaces heavy content with lightweight summary
                summary_content = render_template(
                    "core/engine/fragments/forgotten_summary.j2",
                    tool_name=record.tool_name,
                    original_length=record.original_length,
                    reason=record.reason,
                    summary=record.summary,
                    tool_call_id=msg.tool_call_id,
                )

                # Create new ToolMessage with summary instead of full content
                summary_msg = ToolMessage(
                    content=summary_content,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                    id=msg.id if hasattr(msg, "id") else None,
                    # Preserve metadata for tracking
                    metadata={
                        **(msg.metadata if hasattr(msg, "metadata") and msg.metadata else {}),
                        "forgotten": True,
                        "original_length": record.original_length,
                        "forgotten_reason": record.reason,
                    },
                )
                result.append(summary_msg)
            else:
                result.append(msg)
        else:
            result.append(msg)

    return result


# ==============================================================================
# API Layer Message Folding
# ==============================================================================

def to_base_message(msg: Any) -> BaseMessage | None:
    """
    Convert a database Message record or similar object to a LangChain BaseMessage.
    
    Args:
        msg: Object with role, content, and optionally tool_calls / tool_call_id
        
    Returns:
        A LangChain message object or None if role is unknown
    """
    role = getattr(msg, "role", None)
    content = getattr(msg, "content", "")
    
    # Preserve key metadata that fold_messages and other utilities need
    msg_id = str(getattr(msg, "id", "")) or None
    created_at = getattr(msg, "created_at", None)
    thinking = getattr(msg, "thinking", None)
    
    # LangChain messages use additional_kwargs for extra metadata
    kwargs = {"id": msg_id}
    if created_at:
        kwargs["created_at"] = created_at
    if thinking:
        kwargs["thinking"] = thinking
    if getattr(msg, "steps_snapshot", None):
        kwargs["steps_snapshot"] = msg.steps_snapshot

    if role == "human":
        return HumanMessage(content=content, id=msg_id, additional_kwargs=kwargs)
    elif role == "ai":
        tool_calls = getattr(msg, "tool_calls", [])
        return AIMessage(
            content=content, 
            id=msg_id,
            tool_calls=tool_calls if isinstance(tool_calls, list) else [],
            additional_kwargs=kwargs
        )
    elif role == "tool":
        # For database records, name might be stored in 'tool_name' or derived from tool_calls
        return ToolMessage(
            content=content,
            id=msg_id,
            tool_call_id=getattr(msg, "tool_call_id", ""),
            name=getattr(msg, "tool_name", None),
            additional_kwargs=kwargs
        )
    elif role == "system":
        return SystemMessage(content=content, id=msg_id, additional_kwargs=kwargs)
    
    return None


def fold_messages(messages: list[BaseMessage]) -> list[FoldedMessage]:
    """
    Fold flat message list into nested format with embedded steps.
    
    This version uses MessageFolder for unified logic and supports
    the steps_snapshot fast-path optimization.
    
    Args:
        messages: Flat list of messages (AIMessage, ToolMessage, HumanMessage)
        
    Returns:
        Folded list of FoldedMessage objects
    """
    from app.core.engine.folder import MessageFolder
    return MessageFolder.fold(messages)


# ============================================================================
# Hierarchical Window Slicing (Multi-turn Conversation Support)
# ============================================================================


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
