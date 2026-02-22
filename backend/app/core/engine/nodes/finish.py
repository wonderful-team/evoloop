import logging
from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine
from app.core.engine.state import AgentState
from app.core.engine.prompts.finish import FinishPromptBuilder
from app.core.context.manager import ContextManager
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


def _extract_tool_usage(messages: list) -> str:
    """Extract a summary of tools used in the session to prove activity."""
    from langchain_core.messages import AIMessage
    tools_used = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                tools_used.add(tc["name"])
    
    if not tools_used:
        return "No specific tools were called. Actions were purely conversational."
    return "Tools utilized during session: " + ", ".join(sorted(tools_used))


async def finish_node(state: AgentState, config: RunnableConfig):
    """
    Session Reviewer Agent:
    Audits the current session and decides whether to finalize or backtrack.
    """
    # 1. Resolve Strict Path
    ctx = ContextManager.current()
    cwd = ctx.working_directory or config.get("configurable", {}).get("working_directory")
    
    if not cwd:
        logger.error("Nodes: Finish - No working_directory found. Backtracking.")
        return {"messages": [], "next_node": "supervisor"}

    # 2. Collect context for prompt
    current_plan = state.get("current_plan", "")
    execution_ticket = state.get("execution_ticket")
    verification_status = state.get("verification_status", {})
    
    # 2.1 Action Audit (Universal)
    # Instead of file modifications, we audit what actions (tools) were actually taken.
    messages = state.get("messages", [])
    action_context = _extract_tool_usage(messages)

    # 3. Build Agent System Prompt
    builder = FinishPromptBuilder(
        current_plan=current_plan,
        execution_ticket=execution_ticket,
        verification_status=verification_status,
        action_context=action_context
    )
    system_prompt = builder.build()

    # 3. Define Toolset (Declarative from YAML)
    tools = tool_manager.get_node_tools("finish", state)

    # 4. Run Agent Engine ReAct Loop
    logger.info(f"Nodes: Finish - Starting Session Reviewer loop in {cwd}")
    result = await AgentEngine.run_node(
        state=state,
        config=config,
        system_prompt=system_prompt,
        tools=tools,
        name="Session Reviewer",
        max_steps=20,
    )

    # 5. Handle Terminal Tool Signal
    # If the Reviewer called finalize_session, the tool returns a special string.
    # We need to make sure the graph actually stops.
    # In AgentMain, finish -> END is simple. 
    # But if the Reviewer routed back to operator, AgentEngine handles that routing.
    
    return result
