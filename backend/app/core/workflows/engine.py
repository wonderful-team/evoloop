from typing import List, Dict, Any, Optional
import json
import logging
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage, HumanMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from app.core.workflows.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor
from app.domain.system.service import SystemConfigService

logger = logging.getLogger(__name__)


class AgentEngine:
    """
    Shared execution engine for EvoLoop Agents.
    Centralizes the ReAct loop, context injection, and message repair logic.
    """

    @staticmethod
    async def run_node(
        state: AgentState,
        config: RunnableConfig,
        system_prompt: str,
        tools: List[Any],
        model: str = None,
        max_steps: int = 5,
        temperature: float = 0.7,
        name: str = "Agent"
    ) -> Dict[str, Any]:
        """
        Executes the standard Agent ReAct loop.
        """
        
        # 1. Initialize LLM
        llm = LLMFactory.create_llm(model_name=model, temperature=temperature)
        if tools:
            llm_with_tools = llm.bind_tools(tools)
            tool_map = {t.name: t for t in tools}
        else:
            llm_with_tools = llm
            tool_map = {}

        # 2. Context Injection
        # 2.1 Language Preference
        user_lang = SystemConfigService.get_language_preference()
        
        # 2.2 Project Context (Tree)
        # We try to inject this if not present, but usually it's passed in prompt via formatted string.
        # However, to be safe, we can append a system message if needed.
        # For now, we assume the caller formatted the system_prompt with necessary context.
        # But we DO need to ensure the system prompt includes the language directive if not already.
        
        final_system_prompt = system_prompt
        if "User Language Preference:" not in system_prompt:
            final_system_prompt += f"\n\nUser Language Preference: {user_lang}\nCommunicate in this language."

        # 3. Message Handling & Repair
        messages = list(state.get("messages", []))
        
        # 3.1 Repair Orphaned Tool Messages
        # (Copy-pasted logic from Supervisor/Coder, now centralized)
        valid_tool_ids = set()
        repaired_messages = []
        
        # Check history to build valid_tool_ids set from existing AIMessages
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                 for tc in msg.tool_calls:
                     valid_tool_ids.add(tc['id'])
        
        iterator = iter(messages)
        try:
            while True:
                msg = next(iterator)
                
                if isinstance(msg, ToolMessage):
                    if msg.tool_call_id not in valid_tool_ids:
                        logger.warning(f"🔧 AgentEngine repairing orphaned tool message: {msg.tool_call_id}")
                        # Insert dummy AI message
                        dummy_ai = AIMessage(
                            content="Resuming tool execution...",
                            tool_calls=[{
                                "name": msg.name or "unknown_tool",
                                "args": {},
                                "id": msg.tool_call_id
                            }]
                        )
                        # We must insert it BEFORE this tool message. 
                        # Since we are rebuilding the list, we append dummy then the msg.
                        repaired_messages.append(dummy_ai)
                        valid_tool_ids.add(msg.tool_call_id)
                
                elif isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        valid_tool_ids.add(tc['id'])
                
                elif isinstance(msg, (HumanMessage, SystemMessage)):
                     # Resetting valid IDs on Human message is a strict strategy, 
                     # but in LangGraph history is flat. We should preserve IDs.
                     # The original Supervisor logic reset it. Let's keep it safe.
                     pass

                repaired_messages.append(msg)
        except StopIteration:
            pass
            
        # 4. Loop Execution
        # We construct the messages for the LLM
        # Always prepend System Prompt
        loop_messages = [SystemMessage(content=final_system_prompt)] + repaired_messages[-15:] # Windowing
        
        # LOGGING: Print System Prompt for Debugging (Context/Memory Check)
        logger.debug(f"--- [AgentEngine] System Prompt (First 500 chars) ---\n{final_system_prompt[:500]}...\n-----------------------------------------------------")
        
        new_messages = []
        
        # Tool History for specific loop (avoid immediate repeats)
        local_tool_history = []
        
        for i in range(max_steps):
            logger.info(f"--- {name} Loop Step {i+1} ---")
            
            # Invoke LLM
            response = await llm_with_tools.ainvoke(loop_messages, config=config)
            
            # OBSERVE: LLM Response (Thinking)
            if response.content:
                logger.info(f"[{name}] 🧠 Thinking: {response.content[:300]}..." if len(response.content) > 300 else f"[{name}] 🧠 Thinking: {response.content}")
            
            # Append local conversation
            loop_messages.append(response)
            new_messages.append(response)
            
            if not response.tool_calls:
                # Agent decided to stop (text response)
                logger.info(f"[{name}] 🏁 Finished with text response.")
                break
                
            # Execute Tools
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                # OBSERVE: Tool Call
                logger.info(f"[{name}] 🛠️ Call: {tool_name} | Args: {json.dumps(tool_args)}")
                
                # Check duplication
                tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                if tool_sig in local_tool_history and tool_name != "manage_file": 
                    # Allow manage_file repeats (e.g. read different lines? arg differs)
                    # If exact args match, it is a duplicate.
                    content = f"⚠️ SYSTEM ALERT: You have ALREADY executed `{tool_name}` with these exact arguments. Stop."
                    logger.warning(f"[{name}] 🛑 Prevented duplicate tool: {tool_sig}")
                else:
                    local_tool_history.append(tool_sig)
                    
                    tool = tool_map.get(tool_name)
                    executor = ToolExecutor()
                    
                    if tool:
                        try:
                            content = await executor.execute(tool, tool_args, config=config)
                        except Exception as e:
                            content = f"Error executing {tool_name}: {e}"
                    else:
                        content = f"Error: Tool {tool_name} not found."

                # Create ToolMessage
                tool_msg = ToolMessage(content=str(content), tool_call_id=tool_id, name=tool_name)
                
                # OBSERVE: Tool Result
                log_content = str(content)
                log_snippet = log_content[:200] + "..." if len(log_content) > 200 else log_content
                logger.info(f"[{name}] ✅ Result ({tool_name}): {log_snippet}")
                
                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)
                
        # Return new messages to be appended to state
        return {
            "messages": new_messages
        }
