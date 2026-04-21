"""
User prompt submission hook handler.
"""

from app.core.engine.hooks.core import HookContext, HookResult


async def user_prompt_submit_handler(context: HookContext) -> HookResult:
    """
    Process user prompt before it's handled.

    Useful for:
    - Prompt validation
    - Command shortcuts
    - Context injection
    """
    prompt = context.metadata.get("prompt", "")

    # Example: Command shortcuts
    shortcuts = {
        "/remember": "Please extract and save any important information from our conversation.",
        "/summary": "Please provide a summary of what we've accomplished so far.",
        "/compact": "The context is getting long. Please summarize key points and continue.",
    }

    if prompt in shortcuts:
        modified_context = context
        modified_context.metadata.prompt = shortcuts[prompt]
        return HookResult(
            success=True,
            message=f"Expanded shortcut: {prompt}",
            modified_context=modified_context,
        )

    return HookResult(success=True)
