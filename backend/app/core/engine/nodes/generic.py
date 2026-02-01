import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from app.core.engine.message_utils import smart_window_slice
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor
from app.core.tools.registry import get_tools_by_names
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class GenericNodeConfig(BaseModel):
    system_prompt: str
    tools: list[str] = []
    model: str = None
    temperature: float = 0.7


async def generic_node(
    state: AgentState,
    config: RunnableConfig,
    node_config: dict[str, Any] = None,
):
    """
    A Generic LLM Node that behaves according to the injected `node_config`.
    This allows "Prompt-as-Code" agent definition.
    """
    if not node_config:
        # Should not happen if GraphBuilder binds it correctly
        return {"messages": [AIMessage(content="Error: Generic Node configuration missing.")]}

    # 1. Parse Config
    # We use Pydantic to validate the dict passed from YAML
    cfg = GenericNodeConfig(**node_config)

    # 2. Bind Tools
    tools = get_tools_by_names(cfg.tools)
    tool_map = {t.name: t for t in tools}

    # 3. Create LLM
    llm = LLMFactory.create_llm(model_name=cfg.model, temperature=cfg.temperature)
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    # 4. Prepare Context
    messages = state["messages"]

    # Inject user language preference if available
    user_lang = state.get("user_preferences", "en")
    system_msg = f"{cfg.system_prompt}\n\nUser Language Preference: {user_lang}"

    loop_messages = [SystemMessage(content=system_msg)] + smart_window_slice(messages, window_size=10)

    # 5. ReAct Loop (Simplified)
    # We allow up to 3 turns of tool usage
    state_updates = {}
    for i in range(3):
        logger.info(f"--- GenericNode {node_config.get('id', '?')} Loop {i+1} ---")
        try:
            response = await llm_with_tools.ainvoke(loop_messages, config=config)
            logger.info(f"LLM Response: {response}")
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            raise e

        loop_messages.append(response)

        if not response.tool_calls:
            return {"messages": [response]}

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            tool = tool_map.get(tool_name)
            executor = ToolExecutor()

            if tool:
                # Execute Tool
                try:
                    result = await executor.execute(tool, tool_args, config=config)

                    # [NEW] Check for state mutations
                    # If the tool is 'update_scratchpad', we also want to return the state update!
                    if tool_name == "update_scratchpad":
                        key = tool_args.get("key")
                        val = tool_args.get("value")
                        if "scratchpad" not in state_updates:
                            state_updates["scratchpad"] = {}
                        state_updates["scratchpad"][key] = val

                except Exception as e:
                    result = i18n.get(
                        "prompts.common.tool_execution_error",
                        name=tool_name,
                        error=str(e),
                    )
            else:
                result = i18n.get("prompts.common.tool_not_found", name=tool_name)

            loop_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    # Final response after loop
    final_output = {"messages": [loop_messages[-1]]}
    if state_updates:
        final_output.update(state_updates)
    return final_output
