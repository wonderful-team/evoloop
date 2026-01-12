from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    Lightweight node for casual conversation.
    Does NOT use tools.
    Does NOT use Supervisor planning prompts.
    Does NOT consume large project context.
    """

    # Initialize lightweight LLM
    llm = LLMFactory.create_llm(temperature=0.7)

    # Define a simple Persona Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are EvoLoop, a helpful and intelligent AI coding assistant.
You are currently in 'Chat Mode'.
Your goal is to engage in helpful, friendly conversation with the user.

If the user asks for coding tasks, technical help, or file operations that you cannot handle in this mode, kindly suggest: "I can help with that! Let me switch to my technical workspace." (But for now, just answer generally).

Keep responses concise and friendly.
"""),
        MessagesPlaceholder(variable_name="messages"),
    ])

    chain = prompt | llm

    # We restrict the history to last 10 messages for speed in Chat Mode?
    # Or just pass all. Let's pass all but maybe we should compress if too long.
    # For now, pass all.

    response = await chain.ainvoke(state, config=config)

    return {
        "messages": [response],
        # Chat node usually ends the turn, waiting for user input.
        # So we don't set next_node, or we set it to something that means "wait".
        # In LangGraph, returning from a node usually goes to the next node defined in edge.
        # We will route Chat -> END.
    }
