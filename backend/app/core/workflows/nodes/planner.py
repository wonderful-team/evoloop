import json
from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from app.core.llm.factory import LLMFactory
from app.core.workflows.state import AgentState
from app.domain.planning.tools import create_plan, analyze_feasibility, update_step_status
from app.core.tools.executor import ToolExecutor
from app.core.monitoring.activity import activity_monitor

# --- Planner Prompt ---
planner_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are the **Lead Architect** (Planner) of the system.
    
**Your Goal**: Analyze the user's request and the current project context to create a robust, step-by-step **Implementation Plan**.

**Context**:
Project ID: {project_id}
Current Plan: {current_plan}
System Info: {system_info}

**Responsibilities**:
1. **Analyze**: Understand the user's goal. If unsure, you can verify context, but your main output is a PLAN.
2. **Breakdown**: Split the task into atomic, verifiable steps.
   - Good steps: "Create `api.py`", "Implement `login` function", "Add unit tests".
   - Bad steps: "Do it", "Code functionality".
3. **Verify Feasibility**: The plan must be technically grounded.
4. **Feasibility Check**: You MUST call `analyze_feasibility` on your proposed plan before finalizing it.

**Tools Available**:
- `create_plan(title, steps)`: To save the plan.
- `analyze_feasibility(proposed_plan)`: To check for risks.

**Output Protocol**:
- If a plan already exists but is outdated/failed, UPDATE it or CREATE a new one.
- If no plan exists, CREATE one.
- Once the plan is created and saved (via tool), output "Plan created. Handing off to Supervisor."

**Language**:
- User Language: {user_lang}
- Write plan titles and steps in {user_lang}.
"""),
    ("placeholder", "{messages}"),
])

async def planner_node(state: AgentState, config: RunnableConfig):
    import logging
    logger = logging.getLogger(__name__)
    llm = LLMFactory.create_llm(temperature=0.2) # Low temp for standardized planning
    
    project_id = state.get("project_id", 1)
    
    # 1. Access System Config / Context
    import os, platform
    from app.domain.system.service import SystemConfigService
    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
    user_lang = SystemConfigService.get_language_preference()
    
    # Project Structure (Lightweight)
    project_structure = "Tree not available"
    try:
        from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
        generator = AnnotatedTreeGenerator(cwd, max_depth=2, with_symbols=False, file_limit=20)
        project_structure = await generator.generate()
    except Exception:
        pass

    sys_info = f"OS: {platform.system()}, CWD: {cwd}\nProject Structure:\n{project_structure[:3000]}"
    
    # 2. Update Monitor
    try:
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="PLANNING",
            task_name="Architecting Solution",
            task_status="Breaking down requirements..."
        )
    except Exception:
        pass

    # 3. Bind Tools
    tools = [create_plan, analyze_feasibility]
    llm_with_tools = llm.bind_tools(tools)
    
    # 4. Prepare Chain
    current_plan = state.get("current_plan", "No plan yet.")
    
    chain = planner_prompt.partial(
        project_id=project_id,
        current_plan=current_plan,
        system_info=sys_info,
        user_lang=user_lang
    ) | llm_with_tools

    messages = list(state.get("messages", []))
    new_messages = []
    
    # We allow a small loop for "Propose -> Analyze -> Finalize"
    # Max 3 turns to avoid infinite planning loops
    plan_finalized = False
    
    for i in range(3):
        # Invoke LLM
        response = await chain.ainvoke({"messages": messages}, config=config)
        messages.append(response)
        new_messages.append(response)
        
        if response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                # Execute Tool
                executor = ToolExecutor()
                tool_func = None
                if tool_name == "create_plan":
                    tool_func = create_plan
                    plan_finalized = True # We assume if plan is created, we are done
                elif tool_name == "analyze_feasibility":
                    tool_func = analyze_feasibility
                
                if tool_func:
                    content = await executor.execute(tool_func, tool_args, config=config)
                    
                    # Update State if Plan Created
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
                
                tool_msg = AIMessage(content=str(content)) # Wait, ToolMessage
                from langchain_core.messages import ToolMessage
                tool_msg = ToolMessage(content=str(content), tool_call_id=tool_call["id"], name=tool_name)
                
                messages.append(tool_msg)
                new_messages.append(tool_msg)
        
        # If plan is finalized or LLM says so
        if plan_finalized:
            break
            
        if "handing off" in response.content.lower() or "ready for supervisor" in response.content.lower():
            break

    return {
        "messages": new_messages,
        "current_plan": state.get("current_plan"),
        "structured_plan": state.get("structured_plan"),
        "next_node": "supervisor" # Always go to supervisor to execute the plan
    }
