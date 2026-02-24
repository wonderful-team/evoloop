from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

from app.core.engine.message_utils import repair_message_history
from app.core.engine.prompts import ChatPromptBuilder
from app.core.engine.state import AgentState
from app.infrastructure.llm.factory import LLMFactory


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Lightweight node for casual conversation.
    Does NOT use tools.
    Does NOT use Supervisor planning prompts.
    Does NOT consume large project context.
    """

    # Initialize lightweight LLM
    llm = LLMFactory.create_llm(temperature=0.7)

    # Detect Platform Relevance
    # Filter out existing System Messages from history + Repair
    raw_messages = list(state.get("messages", []))
    history_messages = [m for m in raw_messages if not isinstance(m, SystemMessage)]
    cleaned_messages = repair_message_history(history_messages)

    # Use Builder for Jinja2 prompt
    prompt_builder = ChatPromptBuilder()
    system_prompt = prompt_builder.build()

    # Define a simple prompt template for history
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])

    chain = prompt | llm

    # Invoke with ONLY cleaned history
    response = await chain.ainvoke(
        {
            "messages": cleaned_messages,
        },
        config=config,
    )

    return {
        "messages": [response],
        # Chat node usually ends the turn, waiting for user input.
        # So we don't set next_node, or we set it to something that means "wait".
        # In LangGraph, returning from a node usually goes to the next node defined in edge.
        # We will route Chat -> END.
    }
