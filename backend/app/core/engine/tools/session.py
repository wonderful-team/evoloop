"""Session control tools — replaces L0 builtin actions for natural-language interaction."""

from app.core.shared_state import shared_state
from app.core.tools import evoloop_tool


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.set_agent_name",
)
async def set_agent_name(name: str) -> str:
    """
    Change the assistant's name/call sign for the current session.

    Use this when the user says they want to rename you, e.g. "以后叫我二狗" or
    "我要给你改个名字，叫二狗". If the user mentions a name, set it.
    If no name is given, ask for it.
    """
    name = name.strip("。，？！,.?! ")
    if not name:
        return "你想叫我什么名字？"
    await shared_state.set("agent_name", name)
    return f"好的，以后叫我{name}。"
