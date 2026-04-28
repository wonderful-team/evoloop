from typing import Any

from app.core.tools import evoloop_tool


@evoloop_tool(
    is_state_mutating=True,
    name_map={"zh": "暂存到剪贴板", "en": "Stash to Clipboard"}
)
async def stash_to_clipboard(content: Any, mime_type: str = "text/plain", metadata: dict = None) -> str:
    """
    Stash information (text, image path, UI element bounds) into the agent's short-term workspace clipboard.
    Use this to 'copy' data from one app or step and 'paste' it in another.

    Args:
        content: The data to store. Can be a string, a file path, or a dictionary.
        mime_type: The type of content (e.g., "text/plain", "image/png", "application/json").
        metadata: Optional dictionary with extra context (e.g. {"source_app": "Safari", "field": "email"}).

    Returns:
        Status message. The graph will automatically store this in your 'scratchpad'.
    """
    return f"Successfully stashed {mime_type} to workspace clipboard."


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "从剪贴板检索", "en": "Retrieve from Clipboard"}
)
async def retrieve_from_clipboard() -> str:
    """
    Retrieve all items currently in the workspace clipboard.
    
    Returns:
        A list of currently stashed items. Note: You can usually see these directly in your System Prompt.
    """
    # This tool is a fallback; retrieval is primarily via prompt injection.
    return "Please refer to your System Prompt under 'WORKSPACE CLIPBOARD' to see stashed items."
