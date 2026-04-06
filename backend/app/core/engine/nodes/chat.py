from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine
from app.core.engine.prompts import ChatPromptBuilder
from app.core.engine.state import AgentState
from app.core.engine.tools.memory_tools import recall, remember, search_history

# Lightweight tools for Chat Node (memory-related only)
# Strictly NO file operations, browser, desktop, or command execution
CHAT_TOOLS = [recall, remember, search_history]


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Lightweight node for casual conversation with memory support.
    
    Capabilities:
    - Casual chat and Q&A
    - Recall previously remembered information
    - Search conversation history
    - Remember user preferences
    
    Does NOT use:
    - File operations (use Worker instead)
    - Browser/Desktop automation (use Worker instead)
    - Command execution (use Worker instead)
    
    Note: This node only handles the first message in a conversation.
    Subsequent interactions are routed to Supervisor for better task handling.
    """

    messages = state.get("messages", [])
    
    # Strategy: Only handle pure chat for the first message.
    # For any follow-up or potentially complex interactions, delegate to Supervisor.
    # This avoids the need for hardcoded keyword matching and works for all languages.
    human_message_count = sum(1 for m in messages if hasattr(m, "type") and m.type == "human")
    
    if human_message_count > 1:
        # Not the first interaction - let Supervisor handle it
        return {
            "next_node": "supervisor"
        }

    # Use Builder for Jinja2 system prompt
    prompt_builder = ChatPromptBuilder()
    system_prompt = prompt_builder.build()

    # Get user selected model from config (if any)
    model = config.get("configurable", {}).get("model")

    # Use AgentEngine for unified execution with memory tools
    result = await AgentEngine.run_node(
        state=state,
        config=config,
        system_prompt=system_prompt,
        tools=CHAT_TOOLS,  # ✅ Memory tools only
        model=model,  # Use user selected model
        temperature=0.7,
        name="Chat",
        max_steps=1,       # Single turn, no loop (keeps it lightweight)
        is_subtask=False,  # Not a tool-based subtask
        node_source="chat",
    )

    return {
        "messages": result.get("messages", []),
        "next_node": "END"
    }
