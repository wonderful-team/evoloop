"""
Shared message utilities for agent nodes.

Contains common functions for message processing, history repair, and extraction.
"""

import logging

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.constants import (
    DEFAULT_WINDOW_SIZE, 
    MAX_OUTPUT_LENGTH,
    MAX_CONTEXT_CHARS,
    CONTEXT_PRUNE_THRESHOLD,
    HIERARCHICAL_WINDOW_CONFIG,
)
from app.i18n.service import i18n
from app.infrastructure.llm.model_profile import get_profile

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


def repair_message_history(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Ensure the message history is valid for strict LLM APIs (like Anthropic/GLM).
    1. No orphaned ToolMessages (must have preceding AIMessage with tool_calls).
    2. No dangling ToolCalls (must be followed by ToolMessages).
    3. No consecutive messages of same role (Human->Human, AI->AI).
    4. No empty content allowed.
    """
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
                    ids = [tc["id"] for tc in last.tool_calls]
                    if msg.tool_call_id in ids:
                        is_orphaned = False

            if is_orphaned:
                dummy = AIMessage(
                    content=i18n.get("core_utils.orphaned_tool"),
                    tool_calls=[{
                        "id": msg.tool_call_id,
                        "name": msg.name or "unknown_tool",
                        "args": {}
                    }]
                )
                stage1.append(dummy)

            stage1.append(msg)
            continue

        # Strict Role Alternation (Merge consecutive same-role)
        if stage1:
            last = stage1[-1]
            if type(last) is type(msg) and isinstance(msg, HumanMessage | AIMessage):
                # Merge content
                new_content = f"{last.content}\n\n{msg.content}"
                last.content = new_content
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
                    content=i18n.get("core_utils.interrupted_tool_response"),
                    tool_call_id=tcid,
                    name=tname
                ))
            open_tool_calls = {}

        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                open_tool_calls[tc["id"]] = tc["name"]

        if isinstance(msg, ToolMessage):
            # Clear opened call
            if msg.tool_call_id in open_tool_calls:
                del open_tool_calls[msg.tool_call_id]

        final_repaired.append(msg)

    # Final check for trailing tool calls (history cannot end with AIMessage(tool_calls))
    if open_tool_calls and final_repaired:
        logger.warning(f"🔧 [Repair] History ends with dangling tool calls. Injecting dummy responses.")
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
            final_repaired.insert(first_idx, HumanMessage(content=i18n.get("core_utils.conversation_continuation")))
    elif not final_repaired:
        final_repaired.append(HumanMessage(content=i18n.get("core_utils.conversation_continuation")))

    return final_repaired


def smart_window_slice(
    messages: list[BaseMessage],
    window_size: int | None = None,
    max_total_chars: int = MAX_CONTEXT_CHARS,
    model: str | None = None,
    thread_id: str | None = None,
    user_id: str | None = None,
    project_id: int | None = None,
) -> list[BaseMessage]:
    """
    Slice the message list to a window size, ensuring no (AI -> Tool) pair is split.
    If the window start falls on a ToolMessage, it backtracks to include the parent AIMessage.
    Also enforces a character-based limit (max_total_chars) to prevent Token overflow.

    CRITICAL: Triggers PreCompact hook before slicing to save state.

    Args:
        messages: Full list of messages.
        window_size: Explicit window size. If None, derived from ModelProfile.
        max_total_chars: Maximum total characters allowed in the resulting slice.
        model: Model name for profile-aware window sizing.
        thread_id: Thread ID for hook context.
        user_id: User ID for hook context.
        project_id: Project ID for hook context.

    Returns:
        Sliced list of messages.
    """
    effective_window = window_size or _get_window_size(model)

    # 1. Message Count Based Slicing
    if len(messages) <= effective_window:
        sliced_msgs = messages
    else:
        # CRITICAL: Trigger PreCompact hook BEFORE context is lost
        # This saves task progress, decisions, and state
        if len(messages) > effective_window:
            try:
                from app.core.engine.hooks import hook_system, HookEvent, HookContext
                hook_ctx = HookContext(
                    thread_id=thread_id or "unknown",
                    user_id=user_id,
                    project_id=project_id,
                    messages=messages,
                )
                # Fire and forget - don't block window slicing
                import asyncio
                asyncio.create_task(hook_system.trigger(HookEvent.PRE_COMPACT, hook_ctx))
                logger.debug(f"[Window] PreCompact hook triggered for {thread_id}")
            except Exception as e:
                logger.warning(f"[Window] PreCompact hook failed: {e}")
        
        start_index = max(0, len(messages) - effective_window)
        # Backtrack if starting on a ToolMessage
        while start_index > 0 and isinstance(messages[start_index], ToolMessage):
            start_index -= 1
        sliced_msgs = messages[start_index:]

    def _calc_total_chars(msgs):
        return sum(len(get_message_text(m)) for m in msgs)

    # 2. Content-Level Pre-Pruning (Aggressive truncation for huge tool results in history)
    # This prevents a single 200KB message from consuming the entire window.
    pruned_for_window = []
    for m in sliced_msgs:
        if isinstance(m, ToolMessage) and len(str(m.content)) > CONTEXT_PRUNE_THRESHOLD:
            # We create a clone with truncated content
            truncated_msg = ToolMessage(
                content=str(m.content)[:CONTEXT_PRUNE_THRESHOLD] + "\n... [Output truncated by Window Manager]",
                tool_call_id=m.tool_call_id,
                name=m.name,
                additional_kwargs={**(m.additional_kwargs or {}), "is_truncated": True}
            )
            pruned_for_window.append(truncated_msg)
        else:
            pruned_for_window.append(m)
    
    sliced_msgs = pruned_for_window
    total_chars = _calc_total_chars(sliced_msgs)
    
    if total_chars > max_total_chars:
        logger.warning(f"📉 [Window] Total chars ({total_chars}) exceeds limit ({max_total_chars}). Pruning history.")
        
        # We try to keep the first message (Intent) and the most recent N messages
        first_msg = next((m for m in messages if isinstance(m, HumanMessage)), None)
        
        # Start dropping from the beginning of sliced_msgs (which is already recent history)
        # but always skip the very last few messages to maintain chain of thought
        protected_count = 3  # Keep at least last 3 messages (AI -> Tool -> result)
        
        while len(sliced_msgs) > protected_count and _calc_total_chars(sliced_msgs) > max_total_chars:
            # Check if first message is our protected intent
            if first_msg and sliced_msgs[0] == first_msg:
                # If we have more than protected_count, drop the second one (the oldest non-intent)
                sliced_msgs.pop(1)
            else:
                sliced_msgs.pop(0)

    # Enhance: Preserve the First Human Message (User Goal) if it was sliced out
    # This ensures Supervisor keeps the original context/intent.
    first_human_msg = next((m for m in messages if isinstance(m, HumanMessage)), None)
    if first_human_msg and first_human_msg not in sliced_msgs:
        sliced_msgs.insert(0, first_human_msg)

    return sliced_msgs


def prune_redundant_results(messages: list[BaseMessage], threshold: int = CONTEXT_PRUNE_THRESHOLD) -> list[BaseMessage]:
    """
    Identifies and collapses redundant large tool outputs in message history.
    If the same tool (e.g., read_file) is called multiple times for the same resource,
    previous large outputs are collapsed to save tokens.

    Args:
        messages: List of messages to prune.
        threshold: Character threshold above which a message is considered "large".
    """
    if not messages:
        return messages

    seen_resources = {}  # {resource_key: last_index}
    pruned = list(messages)
    
    # Iterate backwards to keep the most recent ones intact
    for i in range(len(pruned) - 1, -1, -1):
        msg = pruned[i]
        if not isinstance(msg, ToolMessage):
            continue
            
        # Determine resource key (e.g., tool_name:path)
        resource_key = None
        if msg.name == "read_file":
            resource_key = f"read_file"
        elif msg.name == "execute_command":
            resource_key = f"execute_command"

        if not resource_key:
            continue
            
        text = get_message_text(msg)
        if len(text) < threshold:
            continue
            
        if resource_key in seen_resources:
            # This is an older, large result for the same tool type
            # Collapse it
            lines = text.count("\n")
            chars = len(text)
            msg.content = f"[System: Previous large output (Tool: {msg.name}, {lines} lines, {chars} chars) collapsed to save context. Refer to more recent turns for status.]"
            logger.info(f"✂️ [Prune] Collapsed redundant ToolMessage: {msg.name} ({chars} chars)")
        else:
            seen_resources[resource_key] = i
            
    return pruned


# ==============================================================================
# API Layer Message Folding
# ==============================================================================

def fold_messages(messages: list[BaseMessage]) -> list[dict]:
    """
    Fold flat message list into nested format with embedded steps.
    
    This eliminates the need for frontend to perform message folding.
    Tool execution results are nested within their parent AI message as 'steps'.
    
    Args:
        messages: Flat list of messages (AIMessage, ToolMessage, HumanMessage)
        
    Returns:
        Folded list where each AI message contains nested 'steps' array
        
    Example:
        Input:  [AIMessage(tool_calls=[...]), ToolMessage(...), AIMessage(...)]
        Output: [
            {
                role: "ai",
                content: "...",
                tool_calls: [...],
                steps: [{tool: "read_file", output: "...", status: "done"}]
            },
            {role: "ai", content: "...", steps: []}
        ]
    """
    result = []
    i = 0
    
    while i < len(messages):
        msg = messages[i]
        
        if isinstance(msg, AIMessage):
            # Collect tool execution results for this AI message
            steps = []
            tool_calls = msg.tool_calls or []
            
            # Look ahead for ToolMessages matching our tool_calls
            j = i + 1
            tool_call_ids = {tc.get("id"): tc for tc in tool_calls}
            
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tool_msg = messages[j]
                
                # Match with tool_call_id
                tool_call = tool_call_ids.get(tool_msg.tool_call_id)
                
                steps.append({
                    "id": f"step-{tool_msg.tool_call_id}",
                    "tool": tool_msg.name or (tool_call.get("name") if tool_call else "unknown"),
                    "input": tool_call.get("args") if tool_call else {},
                    "output": get_message_text(tool_msg),
                    "status": "done",
                    "tool_call_id": tool_msg.tool_call_id
                })
                j += 1
            
            result.append({
                "id": getattr(msg, "id", f"msg-{i}"),
                "role": "ai",
                "content": get_message_text(msg),
                "thinking": getattr(msg, "thinking", None),
                "tool_calls": tool_calls,
                "steps": steps,
                "timestamp": getattr(msg, "created_at", None)
            })
            
            i = j  # Skip processed ToolMessages
            
        elif isinstance(msg, ToolMessage):
            # Orphan ToolMessage (shouldn't happen after repair, but handle gracefully)
            result.append({
                "id": f"orphan-{msg.tool_call_id}",
                "role": "tool",
                "tool": msg.name or "unknown",
                "output": get_message_text(msg),
                "tool_call_id": msg.tool_call_id,
                "orphan": True
            })
            i += 1
            
        elif isinstance(msg, HumanMessage):
            result.append({
                "id": getattr(msg, "id", f"msg-{i}"),
                "role": "human",
                "content": get_message_text(msg),
                "timestamp": getattr(msg, "created_at", None)
            })
            i += 1
            
        elif isinstance(msg, SystemMessage):
            # System messages usually not shown in chat, but include if needed
            result.append({
                "id": f"system-{i}",
                "role": "system",
                "content": get_message_text(msg)
            })
            i += 1
            
        else:
            # Unknown message type, skip
            i += 1
    
    return result


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
    config = HIERARCHICAL_WINDOW_CONFIG.get(node_source, HIERARCHICAL_WINDOW_CONFIG["default"])
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
            # Collapse tool output to marker (re-executable)
            collapsed = ToolMessage(
                content=f"[{msg.name}] [DONE]",
                tool_call_id=msg.tool_call_id,
                name=msg.name,
                additional_kwargs={
                    **(msg.additional_kwargs or {}),
                    "is_collapsed": True,
                    "original_length": len(str(msg.content)),
                }
            )
            middle_messages.append(collapsed)
            
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
            # Keep topic marker + last N messages that fit
            preserved = [m for m in pruned if getattr(m.additional_kwargs, 'is_topic_marker', False)]
            for m in reversed(pruned):
                if m in preserved:
                    continue
                test_chars = sum(len(get_message_text(x)) for x in preserved + [m])
                if test_chars <= max_total_chars * 0.9:  # 10% buffer
                    preserved.insert(0, m)
            result = preserved
        else:
            result = pruned
    
    return result


def hierarchical_smart_window_slice(
    messages: list[BaseMessage],
    window_size: int | None = None,
    max_total_chars: int = MAX_CONTEXT_CHARS,
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
            from app.core.engine.hooks import hook_system, HookEvent, HookContext
            
            hook_ctx = HookContext(
                thread_id=thread_id or "unknown",
                user_id=user_id,
                project_id=project_id,
                messages=messages,
            )
            # Fire and forget
            import asyncio
            asyncio.create_task(hook_system.trigger(HookEvent.PRE_COMPACT, hook_ctx))
            logger.debug(f"[HierarchicalSlice] PreCompact hook triggered for {thread_id}")
        except Exception as e:
            logger.warning(f"[HierarchicalSlice] PreCompact hook failed: {e}")
    
    # 3. Use hierarchical slicing (no LLM cost)
    return _hierarchical_slice(
        messages=messages,
        effective_window=effective_window,
        max_total_chars=max_total_chars,
        node_source=node_source,
    )
