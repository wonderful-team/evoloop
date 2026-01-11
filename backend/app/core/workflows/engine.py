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

        # [NEW] Inject TraceCallbackHandler for Imitation/Reinforcement Learning
        try:
            from app.core.learning.trace_recorder import TraceCallbackHandler
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            if thread_id and thread_id != "unknown":
                trace_handler = TraceCallbackHandler(thread_id)
                
                # Safely update callbacks
                existing_callbacks = config.get("callbacks", [])
                if existing_callbacks is None:
                    existing_callbacks = []
                elif not isinstance(existing_callbacks, list):
                    # Handle CallbackManager if necessary, but usually generic list here
                    if hasattr(existing_callbacks, "handlers"):
                         existing_callbacks = existing_callbacks.handlers
                    else:
                         existing_callbacks = [existing_callbacks]
                
                # Check duplication to avoid double logging
                has_tracer = any(isinstance(c, TraceCallbackHandler) for c in existing_callbacks)
                
                if not has_tracer:
                    # Create a new config dict to avoid mutating the original globally if shared
                    # But config is usually per-run.
                    config = config.copy()
                    config["callbacks"] = existing_callbacks + [trace_handler]
        except Exception as e:
            logger.warning(f"Failed to inject TraceCallbackHandler: {e}")

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
        raw_messages = list(state.get("messages", []))
        
        # 3.0 Context Pruning (Feature Phase 8: Smart Token Management)
        try:
            from app.core.memory.pruner import ContextPruner
            # Apply pruning to reduce token usage from old tool outputs
            # This modifies the list locally for this turn's prompt construction
            raw_messages = ContextPruner.prune_messages(raw_messages)
        except ImportError:
            pass

        # 3.1 Smart Windowing
        # We want a window of approx N messages, but we MUST NOT split an (AI -> Tool) pair.
        # If the window starts with a ToolMessage, we try to include the preceding AIMessage.
        window_size = 30 # Increased from 15 to 30 for better context
        
        start_index = max(0, len(raw_messages) - window_size)
        
        # If we are cutting off, and the first message in window is a ToolMessage,
        # step back to include the parent AIMessage (if possible).
        while start_index > 0 and isinstance(raw_messages[start_index], ToolMessage):
             start_index -= 1
             
        windowed_messages = raw_messages[start_index:]
        
        # 3.1 Repair Orphaned Tool Messages (ON THE WINDOWED SLICE)
        # We only care about validity within the actual payload sent to LLM.
        messages_to_process = windowed_messages
        
        valid_tool_ids = set()
        repaired_messages = []
        
        # Check history OF THE SLICE to build valid_tool_ids
        for msg in messages_to_process:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                 for tc in msg.tool_calls:
                     valid_tool_ids.add(tc['id'])
        
        iterator = iter(messages_to_process)
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
                        repaired_messages.append(dummy_ai)
                        valid_tool_ids.add(msg.tool_call_id)
                
                elif isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        valid_tool_ids.add(tc['id'])
                
                repaired_messages.append(msg)
        except StopIteration:
            pass
            
        # 4. Loop Execution
        # Always prepend System Prompt
        loop_messages = [SystemMessage(content=final_system_prompt)] + repaired_messages
        
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
                            # --- Diff Tracking Start ---
                            # Only track edits (manage_file, write_to_file)
                            # Assuming "manage_file" is the main edit tool. 
                            # If we have others, we check if they modify files.
                            snapshot_path = None
                            from app.core.memory.diff import diff_tracker
                            
                            if tool_name == "manage_file" and isinstance(tool_args, dict):
                                arg_path = tool_args.get("absolute_path")
                                action = tool_args.get("action")
                                if arg_path and action in ["create", "update_block", "write"]:
                                     snapshot_path = arg_path
                                     diff_tracker.capture_snapshot(snapshot_path)
                                     
                            # Execute Tool
                            content = await executor.execute(tool, tool_args, config=config)
                            
                            # --- Diff Tracking End ---
                            if snapshot_path:
                                diff = diff_tracker.compute_diff(snapshot_path)
                                if diff:
                                    logger.info(f"📝 Diff Detected:\n{diff}")
                                    # Append diff to the tool output for immediate awareness?
                                    # Or store it in a separate memory stream? 
                                    # For now, let's append it to content so LLM sees what it did.
                                    content = str(content) + f"\n\n[Version Control] Changes Applied:\n```diff\n{diff}\n```"
                                else:
                                    # If no diff but success, maybe it was a create or identical replace
                                    pass

                        except Exception as e:
                            content = f"Error executing {tool_name}: {e}"
                    else:
                        content = f"Error: Tool {tool_name} not found."

                # Create ToolMessage
                import uuid
                tool_msg = ToolMessage(content=str(content), tool_call_id=tool_id, name=tool_name, id=str(uuid.uuid4()))
                
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
