import logging
from typing import Any

from langchain_core.messages import RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(is_state_mutating=True)
async def compress_history(
    start_index: int, 
    end_index: int, 
    summary_title: str, 
    summary_content: str,
    _config: RunnableConfig
) -> str:
    """
    Summarizes a range of past messages and replaces them with a single summary message.
    Use this to free up context window space when the conversation becomes too long 
    or contains repetitive terminal outputs.
    
    Args:
        start_index: The index of the first message to include in the summary (0-based).
        end_index: The index of the last message to include (non-inclusive).
        summary_title: A short title for the summary (e.g., "Terminal Cleanup", "Initial Research").
        summary_content: A concise summary of the critical findings or decisions from those messages.
    """
    # NOTE: The actual message removal is handled by the graph state update.
    # We return a signal that includes the summary and the IDs to remove.
    # In a real implementation, the LLM wouldn't know the message IDs directly, 
    # so the engine will have to map these indices to IDs.
    
    summary_block = f"### [HISTORY SUMMARY: {summary_title}]\n{summary_content}"
    
    # This signal will be intercepted by SupervisorNode to yield RemoveMessage delta
    return f"[HISTORY_COMPRESSION_SIGNAL] Range: {start_index}-{end_index} | Summary: {summary_title}"
