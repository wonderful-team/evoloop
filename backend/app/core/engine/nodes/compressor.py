from langchain_core.messages import BaseMessage, RemoveMessage, SystemMessage

from app.core.llm.factory import LLMFactory

import logging
logger = logging.getLogger(__name__)

async def compress_history_delta(messages: list[BaseMessage], keep_last: int = 15) -> list[BaseMessage | RemoveMessage]:
    """
    Generates the delta (Removals + Addition) needed to compress history.
    
    Returns: A list containing:
      - RemoveMessage objects for messages to be deleted.
      - A SystemMessage containing the summary.
    """
    llm = LLMFactory.create_llm()

    if len(messages) <= keep_last + 5: # Buffer
        return []

    # Identification
    system_prompt = messages[0] if isinstance(messages[0], SystemMessage) else None

    # Range to summarize: From 1 (after sys) to len-keep_last
    start_index = 1 if system_prompt else 0
    end_index = len(messages) - keep_last

    to_summarize = messages[start_index:end_index]
    if not to_summarize:
        return []

    conversation_text = ""
    for msg in to_summarize:
        role = msg.type
        content = str(msg.content)
        if len(content) > 2000:
            content = content[:2000] + "...[TRUNCATED]"
        conversation_text += f"{role}: {content}\n"

    # Safety truncation for the whole prompt context
    if len(conversation_text) > 25000:
        conversation_text = conversation_text[:25000] + "\n...[HEAVILY TRUNCATED DUE TO LENGTH]"

    # Language Preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    prompt = f"""You are a Context Compression Expert for a software development assistant.

TASK: Compress the following conversation while preserving ALL critical information.

=== MANDATORY RETENTION LIST ===
You MUST preserve and include in your summary:
1. All file paths and directory structures mentioned
2. All variable names, function names, and class names
3. Specific configurations (ports, API keys, database names, URLs)
4. User preferences and explicit decisions
5. Error messages and their solutions
6. Unresolved questions or pending tasks
7. Tool results and their key outputs

=== FORBIDDEN TO LOSE ===
These MUST appear VERBATIM in your summary if mentioned:
- UUIDs, IDs, or unique identifiers
- Exact code snippets (if under 100 characters)
- URLs and API endpoints
- Version numbers and dependencies
- Authentication tokens or secrets (redacted)

=== CONVERSATION ===
{conversation_text}

=== OUTPUT FORMAT ===
Write a structured summary in {user_lang}:

**[Critical Context]** Key files, configs, and identifiers
**[Decisions Made]** User choices and preferences
**[Pending Tasks]** Unfinished work or open questions
**[Technical Details]** Code patterns, errors, solutions

SUMMARY:
"""

    try:
        summary_response = await llm.ainvoke(prompt, config={"callbacks": []})  # Internal thought, do not stream
        summary_text = summary_response.content

        delta = []

        # 1. Remove old messages
        count = 0
        for msg in to_summarize:
            # We need an ID to remove. If ID is missing, we can't ensure removal in add_messages.
            # However, LangGraph usually adds IDs.
            if msg.id:
                delta.append(RemoveMessage(id=msg.id))
                count += 1
            else:
                 # Fallback: We can't remove messages without ID easily in this paradigm.
                 # But usually they have IDs if coming from StateGraph.
                 pass

        if count == 0:
            # If no IDs found, we abort compression to avoid duplication
            return []

        # 2. Add Summary
        # We insert the summary. But where? add_messages appends.
        # This effectively puts the summary AFTER the System Prompt (which we kept) and BEFORE the recent messages (which we kept).
        # Wait, if we append, it goes to the END.
        # We want the summary to be at the TOP.
        # This is the limitation of `add_messages`. It's append-only (or update by ID).

        # WORKAROUND:
        # If we can't insert at position, we append the summary as a "Context Update" message.
        # "System Announcement: Previous context summarized below..."
        # This is acceptable for the LLM.

        summary_msg = SystemMessage(content=f"**CONTEXT SUMMARY (Previous {len(to_summarize)} messages)**:\n{summary_text}")
        delta.append(summary_msg)

        return delta
    except Exception as e:
        logger.error(f"Compression delta failed: {e}")
        return []
