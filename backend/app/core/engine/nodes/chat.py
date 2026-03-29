from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine import AgentEngine
from app.core.engine.prompts import ChatPromptBuilder
from app.core.engine.state import AgentState


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Lightweight node for casual conversation.
    Does NOT use tools.
    Does NOT use Supervisor planning prompts.
    Does NOT consume large project context.
    
    Uses AgentEngine for unified context management and trace recording.
    """

    # Use Builder for Jinja2 system prompt
    prompt_builder = ChatPromptBuilder()
    system_prompt = prompt_builder.build()

    # Use AgentEngine for unified execution (single-shot mode, no tools)
    result = await AgentEngine.run_node(
        state=state,
        config=config,
        system_prompt=system_prompt,
        tools=[],  # Chat node does not use tools
        temperature=0.7,
        name="Chat",
        max_steps=1,       # Single turn, no loop
        is_subtask=False,  # Not a tool-based subtask
        node_source="chat",  # 👈 标记为 chat 节点，用于语音播报过滤
    )

    return {
        "messages": result.get("messages", []),
        "next_node": "END"
    }
