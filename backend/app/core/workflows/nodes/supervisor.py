from typing import List, Literal, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage, HumanMessage
from langgraph.graph import END

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from app.core.config import settings
from app.core.workflows.state import AgentState

from app.core.llm.factory import LLMFactory
from app.domain.tools.registry import read_document, analyze_feasibility, save_preference, search_concepts
from app.domain.planning.tools import create_plan, update_step_status
import json

llm = LLMFactory.create_llm()

# Supervisor is a decision maker.
# For simplicity, we use a function calling or structured output model.

supervisor_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the Supervisor of an elite coding team.
    
    CRITICAL PROTOCOL:
    1. **Context First**: If user mentions a file/doc, call `read_document` IMMEDIATELY.
    2. **Measure Twice, Cut Once**: Before delegating to `Coder`, you MUST validate your plan.
       - Use `create_plan` tool to draft your approach.
       - Call `analyze_feasibility` with your drafted plan.
       - If the analysis returns "RISKY" or "BLOCKER", refine your plan and analyze again.
       - ONLY when the analysis is "FEASIBLE" (or you have addressed risks) should you route to `Coder`.
    3. **Active Learning**:
       - If the user explicitly states a preference (e.g. "Use pytest", "Don't use X"), call `save_preference` IMMEDIATELY.
       - If you encounter unknown terms, call `search_concepts`.

    4. **Explicit Planning (MANDATORY)**:
       - You MUST call `create_plan` before delegating complex tasks to Coder or Deep Researcher.
       - If the user's request is a single-step question, you can skip planning.
       - But for any "implement", "refactor", or "create" task, a Plan is REQUIRED.
    
    **Direct Response Protocol (Thinking Mode)**:
    - For simple greetings ("Hello"), questions ("What can you do?"), or clarifications:
      - **DO NOT** use tools.
      - **DO NOT** route to Researcher unless external info is needed.
      - Just **reply directly** to the user in the final output.
      - Then route to `finish`.

    Your routing options:
    1. Researcher: For questions, info gathering, or if `analyze_feasibility` reveals missing knowledge.
    2. Coder: ONLY when you have a feasible, verified plan and all context.
    3. Deep Research: For complex investigations.
    4. Documenter: For documentation tasks.
    5. Finish: When done (or after a direct response).
    
    Default to Researcher if unsure.
    
    Current Plan: {current_plan}
    Project ID: {project_id}
    Iteration: {iteration_count}
    System Info: {system_info}
    """),
    ("placeholder", "{messages}"),
    ("system", "Follow the protocol: Read docs, Analyze feasibility, Then decide.")
])

# Define Structured Output for Supervisor
class RoutingDecision(BaseModel):
    """
    Decision on the next step in the workflow.
    """
    next_node: Literal["coder", "deep_researcher", "documenter", "finish", "map_research"] = Field(
        description="The next node to execute. Use 'map_research' if you want to research multiple topics in parallel."
    )
    parallel_research_tasks: Optional[List[str]] = Field(
        default=None,
        description="List of topics to research in parallel. REQUIRED if next_node is 'map_research'."
    )

from langchain_core.runnables import RunnableConfig

async def supervisor_node(state: AgentState, config: RunnableConfig):
    # Context
    project_id = state.get("project_id", 1) # Default to 1 if missing

    # Memory Injection
    if not state.get("user_preferences"):
        try:
            from domain.memory.service import memory_service
            await memory_service.initialize_schema()
            prefs = await memory_service.get_user_preferences("user_default")
            state["user_preferences"] = prefs
        except Exception as e:
            state["user_preferences"] = f"Error fetching preferences: {e}"
            
    # Tool Binding for Reading & Planning
    tools = [read_document, analyze_feasibility, save_preference, search_concepts, create_plan, update_step_status]
    llm_with_tools = llm.bind_tools(tools)
    
    # 1. Tool Loop (Read -> Plan -> Analyze -> Think/Response)
    # Increased loop count to allow: Read Doc -> Analyze Plan -> (maybe Analyze again) -> Decide
    
    # messages = state.get("messages", [])
    # CRITICAL: Copy the list to avoid mutating the state in place!
    # LangGraph state is often a reference. If we mutate it AND return changes, we get duplicates.
    messages = list(state.get("messages", []))
    # We must collect NEW messages to return them as updates
    new_messages = []
    
    current_plan = state.get("current_plan", "No plan yet.")
    iteration_count = state.get("iteration_count", 0)

    # Create a chain for tool calling
    # Gather System Info
    import os, platform
    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
    sys_info = f"OS: {platform.system()} {platform.release()}, CWD: {cwd}"
    
    tool_chain = supervisor_prompt.partial(
        project_id=project_id, 
        current_plan=current_plan, 
        iteration_count=iteration_count,
        system_info=sys_info
    ) | llm_with_tools
    
    # Allow up to 10 turns for planning & analysis
    has_replied_directly = False
    
    for i in range(10):
        # Pass config for streaming callbacks
        result = await tool_chain.ainvoke(state, config=config)
        
        # Check for tool calls
        if hasattr(result, "tool_calls") and result.tool_calls:
            # Append the AI message (Assistant) first - ONCE
            messages.append(result)
            new_messages.append(result)

            # Execute tools
            for tool_call in result.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                content = ""
                if tool_name == "read_document":
                    content = read_document.invoke(tool_args)
                elif tool_name == "analyze_feasibility":
                    content = await analyze_feasibility.ainvoke(tool_args)
                elif tool_name == "save_preference":
                    content = await save_preference.ainvoke(tool_args, config=config)
                elif tool_name == "search_concepts":
                    content = await search_concepts.ainvoke(tool_args, config=config)
                elif tool_name == "create_plan":
                    # Directly invoke the tool function
                    content = create_plan.invoke(tool_args)
                    # Update state based on the plan
                    try:
                        plan_data = json.loads(content)
                        # Create a human readable summary for the prompt
                        steps_text = "\n".join([f"- {s['title']} ({s['status']})" for s in plan_data.get('steps', [])])
                        current_plan = f"Plan: {plan_data.get('title')}\n{steps_text}"
                        state["structured_plan"] = content
                        state["current_plan"] = current_plan
                    except:
                        pass
                elif tool_name == "update_step_status":
                    content = update_step_status.invoke(tool_args)

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
    structured_llm = llm.with_structured_output(RoutingDecision)
    chain = supervisor_prompt.partial(
        project_id=project_id, 
        current_plan=current_plan, 
        iteration_count=iteration_count,
        system_info=sys_info
    ) | structured_llm
    
    next_node = "deep_researcher"
    decision: Optional[RoutingDecision] = None
    try:
        decision = await chain.ainvoke(state, config=config)
        next_node = decision.next_node
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
        "parallel_research_tasks": parallel_research_tasks
    }
