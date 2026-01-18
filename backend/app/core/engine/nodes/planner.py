from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from app.core.engine import repair_message_history
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.core.engine.message_utils import get_message_text
from app.core.tools.executor import ToolExecutor
from app.domain.planning.tools import (
    analyze_feasibility,
    create_plan,
    update_step_status,
)

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
    llm = LLMFactory.create_llm(temperature=0.2)  # Low temp for standardized planning

    project_id = state.get("project_id", 1)

    # 1. Access System Config / Context
    import os

    from app.domain.system.service import SystemConfigService
    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
    user_lang = SystemConfigService.get_language_preference()

    # 4. Prepare Chain
    # Generate Project Structure dynamically
    from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator
    project_structure = "Tree not available"
    try:
        generator = AnnotatedTreeGenerator(cwd, max_depth=2, with_symbols=False, file_limit=20)
        project_structure = await generator.generate()
    except Exception:
        pass

    # Use Builder (Phase 6)
    from app.core.prompts.planner_builder import PlannerPromptBuilder
    from app.domain.planning.manager import PlanManager

    current_plan_json = state.get("structured_plan")
    current_plan_display = PlanManager.format_plan_for_prompt(current_plan_json)

    # 2. Retrieve Past Episodes (Graph-RAG) - Episodic Memory
    past_episodes = ""
    try:
        from app.domain.memory.service import memory_service

        # Determine Goal from Context (Last Human Message)
        user_goal = "General planning"
        for m in reversed(list(state.get("messages", []))):
            if isinstance(m, HumanMessage):
                user_goal = get_message_text(m)
                break

        past_episodes = await memory_service.find_similar_episodes(user_goal, project_id)
    except Exception as e:
        logger.warning(f"Failed to retrieve past episodes: {e}")

    prompt_builder = PlannerPromptBuilder(
        project_id=project_id,
        current_plan=current_plan_display,
        context={
            "project_structure": project_structure[:3000],
            "past_experience": past_episodes
        }
    )

    system_msg = prompt_builder.build(config)

    # Bind planning tools to LLM
    tools = [create_plan, analyze_feasibility, update_step_status]
    llm_with_tools = llm.bind_tools(tools)

    # Create simple prompt template with system injection
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("placeholder", "{messages}"),
    ])

    chain = prompt | llm_with_tools

    # Filter SystemMessages to avoid duplication/protocol errors (Fix 5.0)

    # 1. Filter out SystemMessages
    raw_messages = [m for m in state.get("messages", []) if not isinstance(m, SystemMessage)]
    # 2. Repair history (inject dummy AIMessages if ToolMessages are orphaned)
    messages = repair_message_history(raw_messages)

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
                    plan_finalized = True
                elif tool_name == "analyze_feasibility":
                    tool_func = analyze_feasibility
                elif tool_name == "update_step_status":
                    tool_func = update_step_status

                if tool_func:
                    content = await executor.execute(tool_func, tool_args, config=config)

                    # Update State if Plan Created/Updated
                    if tool_name == "create_plan":
                        try:
                            # Content is JSON string from tool
                            state["structured_plan"] = str(content)
                            state["current_plan"] = PlanManager.format_plan_for_prompt(str(content))
                        except:
                            pass
                else:
                    content = f"Error: Tool {tool_name} not found."

                from langchain_core.messages import ToolMessage
                tool_msg = ToolMessage(content=str(content), tool_call_id=tool_call["id"], name=tool_name)

                messages.append(tool_msg)
                new_messages.append(tool_msg)

        # If plan is finalized or LLM says so
        if plan_finalized:
            break

        # Helper to extract text from content (which might be list or string)
        content_text = get_message_text(response)

        if "handing off" in content_text.lower() or "ready for supervisor" in content_text.lower():
            break

    return {
        "messages": new_messages,
        "current_plan": state.get("current_plan"),
        "structured_plan": state.get("structured_plan"),
        "next_node": "supervisor"
    }
