from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from app.core.engine.message_utils import repair_message_history
from app.core.engine.state import AgentState
from app.infrastructure.llm.factory import LLMFactory
from app.i18n.service import i18n


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
    from app.core.environment.prompt_utils import build_environment_prompt, detect_platform_relevance
    
    # Filter out existing System Messages from history + Repair
    raw_messages = list(state.get("messages", []))
    history_messages = [m for m in raw_messages if not isinstance(m, SystemMessage)]
    cleaned_messages = repair_message_history(history_messages)

    relevance = detect_platform_relevance(raw_messages)
    env_info = build_environment_prompt(relevance=relevance)

    # Define a simple Persona Prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are EvoLoop, a helpful and intelligent AI coding assistant.
You are currently in 'Chat Mode'.
Your goal is to engage in helpful, friendly conversation with the user.

## Environment Awareness
{env_info}

If the user asks for coding tasks, technical help, or file operations that you cannot handle in this mode, kindly suggest: "I can help with that! Let me switch to my technical workspace." (But for now, just answer generally).

Keep responses concise and friendly.

{lang_instruction}
"""),
        MessagesPlaceholder(variable_name="messages"),
    ])

    chain = prompt | llm

    # We restrict the history to last 10 messages for speed in Chat Mode?
    # Or just pass all. Let's pass all but maybe we should compress if too long.
    # For now, pass all.

    # Filter out existing System Messages from history + Repair
    # (Moved to top for relevance detection)

    # Language preference
    from app.infrastructure.config.service import SystemConfigService

    user_lang = SystemConfigService.get_language_preference()

    # Invoke with ONLY cleaned history (System prompt is in chain)
    response = await chain.ainvoke(
        {
            "messages": cleaned_messages,
            "lang_instruction": i18n.get("prompts.chat.lang_instruction", language=user_lang),
            "env_info": env_info,
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
