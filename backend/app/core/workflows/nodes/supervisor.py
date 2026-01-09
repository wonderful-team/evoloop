import json
from typing import List, Literal, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from app.core.config import settings
from app.core.workflows.state import AgentState

from app.core.llm.factory import LLMFactory
from app.core.tools.executor import ToolExecutor
from app.domain.tools.memory import save_preference, search_concepts
from app.domain.tools.facades import manage_file
from app.domain.tools.facades import manage_file
# from app.domain.planning.tools import create_plan, update_step_status, analyze_feasibility -> Moved to Planner Node

# llm = LLMFactory.create_llm()

# Supervisor is a decision maker.
# For simplicity, we use a function calling or structured output model.

supervisor_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the Supervisor of an elite coding team.
    
    **MISSION**: Your goal is to PREPARE the workspace for specialized workers (Coder, Deep Researcher). You do not write code yourself; you Analyze, Plan, and Route.

    **WORKFLOW PHASES**:
    1. **Explore**: If uncertain, use `manage_file` to inspect the directory tree or read critical documents.
    # 2. Plan (DELEGATED):
    # If the task is complex and you do not have a `current_plan` in the context,
    # you MUST route to `planner` node. Do NOT try to plan yourself.
    # Just output: `next_node="planner"`.
    #
    # If you have a plan, follow it.

    # 3. Verify:
    # After Coder finishes, if you need to run tests, route to `coder` with `run_tests` instructions (or specialized tester).

    # 4. Handoff:
    # When tasks are done, route to `finish`. and signal the next step.

    **CRITICAL PROTOCOL**:
    1. **Context First**: 
       - If you are unsure about the file structure, call `manage_file(action='list_tree')` FIRST.
       - If user mentions a file/doc, call `manage_file(action='read')` IMMEDIATELY.

    2. **Explicit Planning (MANDATORY)**:
       - You MUST call `create_plan` before delegating complex tasks to Coder.
       - If the user's request is a single-step question, you can skip planning.
       
    3. **Active Learning**:
       - If user states a preference (e.g., "Use pytest"), call `save_preference`.
       - If you complete a task, call `harvest_knowledge`.

    4. **Language Protocol**:
       - User Language: {user_lang}
       - Communicate in this language.

    **EXIT / HANDOFF STRATEGY**:
    - **To Coder**: When you have a solid, feasible plan -> Output: "Plan verified. Ready for Coder." (STOP calling tools).
    - **To Researcher**: If you need deep investigation -> Output: "Need more research on X." (STOP calling tools).
    - **Direct Reply**: For simple questions -> Output the answer text directly.

    **Dynamic HITL Protocol**:
    - Use `request_human_input` if ambiguous or risky. System will pause.

    **Think Before Action**:
    - **CHECK HISTORY**: Before calling ANY tool, check if you have just performed this action.
    - **CHECK FOR ANSWER**: If the conversation history shows you have ALREADY answered the user's question, DO NOT explore again.
      - Output: "I have provided the answer above. Task completed."
      - This will effectively trigger the "finish" route.
    - **AVOID REDUNDANCY**: If you have already read a file or searched a query and received a valid result, DO NOT repeat it.
    - Explain WHY: "I will read the file `main.py` to check imports." or "I see I have already read `main.py`, proceeding to analysis."
    Current Plan: {current_plan}
    Project ID: {project_id}
    Iteration: {iteration_count}
    System Info: {system_info}
    """),
    ("placeholder", "{messages}"),
    ("system", "Follow protocol: Explore -> Plan -> Handoff. Do not code directly.")
])


# Define Structured Output for Supervisor
class RoutingDecision(BaseModel):
    """
    Decision on the next step in the workflow.
    """
    next_node: Literal["planner", "coder", "deep_researcher", "documenter", "finish", "map_research", "requirement_analyst"] = Field(
        description="The next worker node to route to. Default to 'finish' if done."
    )
    parallel_research_tasks: Optional[List[str]] = Field(
        default=None,
        description="List of topics to research in parallel. REQUIRED if next_node is 'map_research'."
    )
    
    # Orchestration Fields (Phase 3.0)
    tool_profile: Optional[Literal["GENERAL", "DEVOPS", "RESEARCH"]] = Field(
        default="GENERAL",
        description="The tool profile to activate for the Coder. Use 'DEVOPS' for k8s/docker/aws, 'RESEARCH' for analysis, 'GENERAL' for coding."
    )
    retrieval_query: Optional[str] = Field(
        default=None,
        description="Optional keywords to retrieve specialized tools from database (e.g. 'kubernetes deployment', 'aws s3')."
    )


async def supervisor_node(state: AgentState, config: RunnableConfig):
    import logging
    logger = logging.getLogger(__name__)
    llm = LLMFactory.create_llm()
    # Context
    project_id = state.get("project_id", 1)  # Default to 1 if missing

    # OPTIMIZATION: Emit "Thinking" status immediately for UI responsiveness
    try:
        from app.core.monitoring.activity import activity_monitor
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="PLANNING",
            task_name="Supervisor Decision",
            task_status="Analyzing context and tools..."
        )
    except Exception:
        pass

    # 0. Context Compression Check
    try:
        from app.core.workflows.nodes.compressor import compress_history_delta
        # Check current messages length
        current_msgs = state.get("messages", [])
        delta = await compress_history_delta(current_msgs)
        if delta:
            # Return delta to compress history and restart supervisor
            return {
                "messages": delta,
                "next_node": "supervisor"
            }
    except Exception as e:
        # Fallback to normal execution if compression fails
        # Log error? 
        pass

    # 0.5 Skill Matching Hook (Imitation Learning Phase 3/4)
    # Check if user's request matches a learned skill BEFORE standard LLM processing
    try:
        from app.core.learning.skill_executor import skill_matcher, SkillExecutor
        from app.domain.tools.registry import get_supervisor_tools
        from app.infrastructure.mcp.client import mcp_client_manager

        # Get last user message
        current_msgs = state.get("messages", [])
        last_human_msg = None
        for msg in reversed(current_msgs):
            if isinstance(msg, HumanMessage):
                last_human_msg = msg.content
                break

        if last_human_msg and not state.get("skill_execution_attempted"):
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            match = await skill_matcher.match(last_human_msg, threshold=0.7, thread_id=thread_id)

            if match:
                logger.info(f"🎯 Skill Match Found: '{match.skill_name}' (confidence: {match.confidence:.2f})")

                # Build tool registry for execution
                core_tools = get_supervisor_tools()
                mcp_tools = mcp_client_manager.get_tools()
                tool_registry = {t.name: t for t in core_tools + mcp_tools}

                # Execute skill
                executor = SkillExecutor(config)
                success, result = await executor.execute_skill(
                    match.skill_id,
                    match.extracted_params,
                    tool_registry
                )

                # Create response message
                if success:
                    response_content = f"✅ Executed skill '{match.skill_name}':\n{result}"
                else:
                    response_content = f"⚠️ Skill '{match.skill_name}' partially failed:\n{result}"

                # Return with skill execution result, skip to finish
                return {
                    "messages": [AIMessage(content=response_content)],
                    "next_node": "finish",
                    "skill_execution_attempted": True
                }
    except Exception as e:
        logger.warning(f"Skill matching failed, falling back to standard processing: {e}")
        # Mark as attempted to avoid retry loops
        state["skill_execution_attempted"] = True

    # Initialize messages early
    messages = list(state.get("messages", []))
    new_messages = []

    # Memory Injection
    if not state.get("user_preferences"):
        try:
            from domain.memory.service import memory_service
            await memory_service.initialize_schema()
            prefs = await memory_service.get_user_preferences("user_default")
            state["user_preferences"] = prefs
        except Exception as e:
            state["user_preferences"] = f"Error fetching preferences: {e}"

    # Tool Binding with Semantic Retrieval
    from app.infrastructure.mcp.client import mcp_client_manager
    from app.domain.tools.retrieval import tool_retriever
    from app.domain.tools.registry import get_supervisor_tools

    # 1. Core Tools (Always Active)
    core_tools = get_supervisor_tools()

    # 2. Candidate Tools (MCP)
    mcp_tools = mcp_client_manager.get_tools()

    # 3. Retrieve Relevant Tools
    # Ensure candidates are indexed (idempotent)
    await tool_retriever.index_tools(mcp_tools)

    # Context for retrieval
    query_context = state.get("task_status", "General task")
    last_msg = ""
    if messages and isinstance(messages[-1].content, str):
        last_msg = messages[-1].content
        query_context += f" {last_msg}"

    # Semantic Concept Injection (Active Knowledge)
    project_concepts = ""
    try:
        from app.domain.memory.service import memory_service
        # Search using the last message as query
        if last_msg:
            found_concepts = await memory_service.search_concepts(last_msg, project_id)
            if found_concepts and "No relevant concepts" not in found_concepts:
                project_concepts = f"\nRelevant Project Concepts:\n{found_concepts}"
    except Exception as e:
        project_concepts = f"\n(Concept Search Failed: {e})"

    # Fetch top relevant tools
    retrieved_tools = await tool_retriever.retrieve(query_context, k=15)

    # Combine (Core + Retrieved)
    # Use a dict by name to deduplicate in case of overlap
    tool_dict = {t.name: t for t in core_tools + retrieved_tools}
    tools = list(tool_dict.values())

    llm_with_tools = llm.bind_tools(tools)

    # 1. Tool Loop (Read -> Plan -> Analyze -> Think/Response)
    # Increased loop count to allow: Read Doc -> Analyze Plan -> (maybe Analyze again) -> Decide

    # messages list is already initialized above

    current_plan = state.get("current_plan", "No plan yet.")
    iteration_count = state.get("iteration_count", 0)

    # Create a chain for tool calling
    # Gather System Info
    import os, platform
    from app.domain.system.service import SystemConfigService

    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()

    # Language Preference (Synced with Frontend)
    user_lang = SystemConfigService.get_language_preference()

    # Context Injection Phase
    # 1. Project Structure (Tree)
    project_structure = "Tree not available"
    try:
        # Use underlying Generator directly (Smart Truncation)
        from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator

        # Limit depth to 3 and files per dir to 30 for tokens safety
        generator = AnnotatedTreeGenerator(cwd, max_depth=3, with_symbols=False, file_limit=30)
        project_structure = await generator.generate()

    except Exception as e:
        project_structure = f"Tree error: {e}"

    # Limit size
    sys_info = f"OS: {platform.system()} {platform.release()}, CWD: {cwd}\nLanguage Preference: {user_lang}\n\nProject Structure:\n{project_structure[:5000]}{project_concepts}"

    # Allow up to 10 turns for planning & analysis
    has_replied_directly = False

    for i in range(10):
        # Refresh Context for Prompt (Critical for Plan updates)
        current_plan = state.get("current_plan", "No plan yet.")
        iteration_count = state.get("iteration_count", 0)

        tool_chain = supervisor_prompt.partial(
            project_id=project_id,
            current_plan=current_plan,
            iteration_count=iteration_count,
            system_info=sys_info,
            user_lang=user_lang
        ) | llm_with_tools
        # Initialize logger
        # logger = logging.getLogger(__name__)

        # Sanitize / Repair Messages
        # Verify that every ToolMessage is preceded by an AIMessage with matching tool_calls
        # Fix: Support Parallel Tool Calls (AI -> Tool1 -> Tool2)
        repaired_messages = []
        valid_tool_ids = set()

        iterator = iter(messages)
        try:
            while True:
                msg = next(iterator)

                if isinstance(msg, AIMessage) and msg.tool_calls:
                    valid_tool_ids = {tc['id'] for tc in msg.tool_calls}
                elif isinstance(msg, ToolMessage):
                    if msg.tool_call_id not in valid_tool_ids:
                        # is_orphan = True
                        logger.debug(f"🔧 REPAIRING ORPHANED TOOL MESSAGE: {msg.tool_call_id}")
                        # Create a dummy AI message that 'calls' this tool
                        dummy_ai = AIMessage(
                            content="Resuming tool execution...",
                            tool_calls=[{
                                "name": msg.name or "unknown_tool",
                                "args": {},
                                "id": msg.tool_call_id
                            }]
                        )
                        repaired_messages.append(dummy_ai)
                        # Now it's valid for this dummy
                        valid_tool_ids.add(msg.tool_call_id)
                elif isinstance(msg, (HumanMessage, SystemMessage)):
                    # Reset valid tools on new turn
                    valid_tool_ids = set()

                repaired_messages.append(msg)

        except StopIteration:
            pass

        # Update state temporarily for this invocation
        state["messages"] = repaired_messages

        # Pass config for streaming callbacks
        result = await tool_chain.ainvoke(state, config=config)
        logger.info(f"LLM Response: {result.content}")

        # Check for tool calls
        if hasattr(result, "tool_calls") and result.tool_calls:
            # Append the AI message (Assistant) first - ONCE
            messages.append(result)
            new_messages.append(result)

            # Create tool map for easy lookup
            tool_map = {t.name: t for t in tools}

            # Track executed tools in this session to prevent loops
            # We use a simple signature: name + sorted(args.items())
            if "tool_history" not in state:
                state["tool_history"] = []

            # Execute tools
            for tool_call in result.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Check for duplication
                import json
                try:
                    # Normalize args for comparison
                    tool_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                except:
                    tool_sig = f"{tool_name}:{str(tool_args)}"

                content = ""
                is_duplicate = False

                # Check duplication against local state history
                if tool_sig in state["tool_history"]:
                    content = f"⚠️ SYSTEM ALERT: You have ALREADY executed `{tool_name}` with these exact arguments. Do not repeat actions. Review the history to see the results. Proceed to the next step."
                    is_duplicate = True
                    logger.warning(f"Prevented duplicate tool call: {tool_sig}")
                else:
                    state["tool_history"].append(tool_sig)

                if not is_duplicate:
                    if tool_name in tool_map:
                        selected_tool = tool_map[tool_name]
                        executor = ToolExecutor()

                        # Universal async invocation with observability
                        content = await executor.execute(selected_tool, tool_args, config=config)

                        # Special Handling for State Updates (create_plan)
                        if tool_name == "create_plan":
                            try:
                                plan_data = json.loads(str(content))
                                steps_text = "\\n".join([f"- {s['title']} ({s['status']})" for s in plan_data.get('steps', [])])
                                current_plan = f"Plan: {plan_data.get('title')}\\n{steps_text}"
                                state["structured_plan"] = str(content)
                                state["current_plan"] = current_plan
                            except:
                                pass
                    else:
                        content = f"Error: Tool {tool_name} not found."

                # Create tool message
                tool_msg = ToolMessage(content=str(content), tool_call_id=tool_call["id"], name=tool_name)

                # Update state messages
                messages.append(tool_msg)
                new_messages.append(tool_msg)

            # Update local state for next iteration (after all tools processed)
            state["messages"] = messages

            # Continue loop
            continue

        # Check for direct text response (Thinking Mode)
        elif result.content:
            # The LLM provided a direct response (e.g. "Hello! I can help you with...")
            # We treat this as a valid step and append it.
            messages.append(result)
            new_messages.append(result)
            state["messages"] = messages
            has_replied_directly = True
            # We break because we got a response, now we decide where to go (likely Finish)
            break

        else:
            # No tool call, no content? Just break ready to decide
            break

    # 2. Make Routing Decision

    # HEURISTIC: Check if we just received a Deep Research Report
    if messages and isinstance(messages[-1], AIMessage):
        last_content = messages[-1].content
        if "Full Research Report" in last_content or "Detailed Conclusion" in last_content or "# Final Conclusion" in last_content:
            logger.info("Supervisor detected Research Report. Defaulting to FINISH to avoid loops.")
            return {
                "next_node": "finish",
                "messages": new_messages,
                "current_plan": state.get("current_plan"),
                "structured_plan": state.get("structured_plan"),
                "parallel_research_tasks": []
            }

    # HEURISTIC: Check if we just requested Human Input
    # If the last tool call was `request_human_input`, we must STOP and wait (route to finish).
    # The system will resume later with the user's input.
    if messages and isinstance(messages[-1], ToolMessage):
        if messages[-1].name == "request_human_input" or messages[-1].name == "request_approval":
            logger.info("Human Input requested. Creating interrupt point (finish).")
            return {
                "next_node": "finish",
                "messages": new_messages,
                "current_plan": state.get("current_plan"),
            }

    from langchain_core.output_parsers import JsonOutputParser
    parser = JsonOutputParser(pydantic_object=RoutingDecision)
    format_instructions = parser.get_format_instructions()

    routing_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are the Supervisor. Decide the next step.
        
        Options:
        - "requirement_analyst": IF the user's request is AMBIGUOUS, VAGUE, or a NEW PROJECT Idea. Run this to clarify requirements BEFORE planning.
        - "planner": If requirements are clear but complex, and you need a step-by-step Technical Plan.
        - "coder": If you have a plan and need to write code.
        - "deep_researcher": If you need to search, read docs, or investigate complex topics.
        - "documenter": If you need to write documentation.
        - "finish": If the user's request is fully satisfied, OR if you have replied directly to a general question (e.g. "What can you do?").
        
        CRITICAL EXIT CRITERIA (CHECK FIRST):
        1. **Direct Answer Provided**: If the LAST message from the AI (Supervisor) contains a direct answer to the user's question (e.g. "The project is...", "I have fixed..."), YOU MUST CHOOSE "finish".
        2. **Task Completed**: If the Agent says "Done", "Fixed", or "Plan is ready for Coder" -> Route accordingly (Finish or Coder).
        
        Specific Rules:
        - If Request is Vague ("Build a blog") -> Route to "requirement_analyst".
        - If YOU (System) just asked Clarifying Questions -> Route to "finish" (wait for user reply).
        - If User Replied to Questions -> Route to "requirement_analyst" (to summarize).
        - If Agent says "Plan verified. Ready for Coder" -> Route to "coder".
        - If Agent says "Need more research" -> Route to "deep_researcher".
        - If Agent provided the answer -> Route to "finish".
        
        **ORCHESTRATION (TOOLING CONTROL)**:
        - When routing to "coder", you MUST decide the appropriate Tool Profile:
          - "DEVOPS": If task involves Docker, K8s, AWS, Terraform, or shell scripts.
          - "RESEARCH": If task is purely reading/analyzing code or docs without modification.
          - "GENERAL": Default for most coding tasks.
        - You can also provide a `retrieval_query` to load specialized tools (e.g. "kubernetes deployment", "aws s3 buckets").
        
        You MUST output a JSON object matching the schema.
        "next_node" is REQUIRED.
        
        {format_instructions}
        
        system_info: {system_info}
        """),
        ("placeholder", "{messages}"),
        ("system", "Analyze the above conversation. Has the question been answered? If yes, route to finish. Output ONLY the JSON object."),
    ])

    chain = routing_prompt.partial(
        system_info=sys_info,
        format_instructions=format_instructions
    ) | llm | parser

    next_node = "deep_researcher"
    decision: Optional[RoutingDecision] = None
    try:
        # Create a clean config without callbacks to hide internal routing logic from user
        # We don't want "Thinking..." or raw JSON to appear in chat for this metadata step.
        routing_config = config.copy() if config else {}
        # CRITICAL: We must explicitly set to empty list to override parent context callbacks!
        # Deleting the key causes it to inherit from parent context.
        routing_config["callbacks"] = []

        if "configurable" in routing_config:
            # Keep configurable but ensure we don't accidentally pass other tracking metadata if needed
            pass

        raw_decision = await chain.ainvoke(state, config=routing_config)
        # Parse manually into Pydantic to ensure validation
        decision = RoutingDecision(**raw_decision)
        next_node = decision.next_node
    except InterruptedError:
        raise
    except Exception as e:
        # Fallback if structured output fails
        next_node = "deep_researcher"

    # CRITICAL: Return the new messages so LangGraph persists them!
    # If we return "messages": new_messages, LangGraph's reducer (operator.add) will append them.
    # If map_research is chosen but no tasks, fallback
    parallel_research_tasks = []
    if decision:
        if next_node == "map_research" and not decision.parallel_research_tasks:
            next_node = "deep_researcher"
        parallel_research_tasks = decision.parallel_research_tasks or []

    return {
        "next_node": next_node,
        "messages": new_messages,
        "current_plan": state.get("current_plan"),
        "structured_plan": state.get("structured_plan"),
        "parallel_research_tasks": parallel_research_tasks,
        
        # Orchestration (Phase 3.0)
        "active_tool_profile": decision.tool_profile if decision else "GENERAL",
        "tool_retrieval_query": decision.retrieval_query if decision else None
    }
