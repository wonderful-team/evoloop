import logging
import os

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.i18n.service import i18n
from app.core.engine.message_utils import get_message_text, smart_window_slice
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.domain.memory.service import memory_service

logger = logging.getLogger(__name__)


class HarvestedConcept(BaseModel):
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of what it is and how it was used")


class ProactiveTodo(BaseModel):
    should_create: bool = Field(description="Whether a todo should be created")
    title: str | None = Field(description="Title of the todo")
    due_date: str | None = Field(description="Due date in relative format (e.g. '1 hour') or ISO")
    reason: str | None = Field(description="Why this todo is needed")


class SessionConclusion(BaseModel):
    """Unified output for finish node - combines summary, knowledge harvesting, and todo detection."""
    summary: str = Field(description="Human-readable summary of what was accomplished in this session")
    harvested_concepts: list[HarvestedConcept] = Field(
        default_factory=list,
        description="Key concepts, patterns, or decisions worth remembering for future tasks"
    )
    proactive_todo: ProactiveTodo | None = Field(
        default=None,
        description="A todo item if any follow-up action was mentioned"
    )


async def finish_node(state: AgentState, config: RunnableConfig):
    """
    Finalize the workflow with unified SessionConclusion.
    
    Single LLM call produces:
    1. Human-readable summary (returned to user)
    2. Harvested concepts (stored in Neo4j)
    3. Proactive todo (created if applicable)
    """
    logger.info("Nodes: Finish - Generating Session Conclusion")

    # 1. Collect Context
    messages = state.get("messages", [])
    tool_history = state.get("tool_history", [])
    project_id = state.get("project_id", 1)
    current_plan = state.get("current_plan", "")

    # Language preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    # 2. Build Context Summary
    recent_history = smart_window_slice(messages, window_size=15)
    
    # Tool history summary (for context enrichment)
    tool_summary = "None"
    if tool_history:
        # Extract unique tool names for summary
        unique_tools = list(set([sig.split(":")[0] for sig in tool_history if ":" in sig]))
        tool_summary = ", ".join(unique_tools) if unique_tools else "None"

    # Optional: Git diff context (if available)
    git_context = ""
    cwd = config.get("configurable", {}).get("working_directory") or os.getcwd()
    if os.path.exists(os.path.join(cwd, ".git")):
        try:
            import subprocess
            result = subprocess.run(
                ["git", "diff", "HEAD", "--stat"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.stdout.strip():
                git_context = f"\n**Git Changes (Uncommitted):**\n```\n{result.stdout[:500]}\n```"
        except Exception:
            pass

    # 3. Unified Prompt
    conclusion_prompt = f"""You are the EvoLoop Session Analyst.
The user's task has been completed. Analyze the conversation and provide a structured conclusion.

**User Language Preference**: {user_lang}

**Task Plan (if any)**: {current_plan[:1000] if current_plan else "No formal plan"}

**Tools Used**: {tool_summary}
{git_context}

### Instructions

1. **summary**: Write a concise, professional summary of what was accomplished.
   - Use the user's preferred language ({user_lang})
   - Mention key actions taken and outcomes
   - Use Markdown formatting with bullet points if appropriate

2. **harvested_concepts**: Extract up to 5 concepts worth remembering:
   - Technologies, patterns, or architecture decisions used
   - Domain-specific terms or configurations
   - NOT generic programming terms (like "function", "variable")
   - Each concept needs a name and description

3. **proactive_todo**: If the conversation mentioned any follow-up tasks:
   - "I'll deploy this later", "Check the logs in 30 minutes", etc.
   - Set should_create=true only if a real action is needed later
   - Ignore completed tasks or generic statements

Analyze the conversation and respond with the SessionConclusion structure.
"""

    # 4. Single LLM Call with Structured Output
    llm = LLMFactory.create_llm(temperature=0.3)
    structured_llm = llm.with_structured_output(SessionConclusion)

    messages_for_analysis = [SystemMessage(content=conclusion_prompt)] + recent_history

    try:
        conclusion = await structured_llm.ainvoke(messages_for_analysis, config={"callbacks": []})
    except Exception as e:
        logger.error(f"Failed to generate SessionConclusion: {e}")
        # Fallback to simple response
        return {
            "messages": [AIMessage(content="✅ Task completed.")]
        }

    if not conclusion:
        logger.warning("LLM returned None for SessionConclusion")
        return {
            "messages": [AIMessage(content="✅ Task completed.")]
        }

    # 5. Process Results

    # 5a. Store harvested concepts in Neo4j
    if conclusion.harvested_concepts:
        for concept in conclusion.harvested_concepts:
            try:
                await memory_service.add_concept(
                    name=concept.name,
                    description=concept.description,
                    project_id=project_id,
                    related_files=[]
                )
                logger.info(f"Harvested concept: {concept.name}")
            except Exception as e:
                logger.warning(f"Failed to store concept {concept.name}: {e}")

    # 5b. Create proactive todo if needed
    todo_notice = ""
    if conclusion.proactive_todo and conclusion.proactive_todo.should_create and conclusion.proactive_todo.title:
        try:
            from app.domain.tools.manage_todo import manage_todo
            await manage_todo.ainvoke(
                {
                    "action": "add",
                    "title": conclusion.proactive_todo.title,
                    "due_date": conclusion.proactive_todo.due_date,
                    "category": "proactive",
                    "priority": "medium",
                    "description": f"Auto-created: {conclusion.proactive_todo.reason}"
                },
                config=config
            )
            todo_notice = i18n.get(
                "prompts.finish.proactive_reminder",
                title=conclusion.proactive_todo.title
            )
            logger.info(f"Created proactive todo: {conclusion.proactive_todo.title}")
        except Exception as e:
            logger.warning(f"Failed to create proactive todo: {e}")

    # 5c. Build final message
    final_summary = conclusion.summary
    
    # Append harvested concepts notice if any
    if conclusion.harvested_concepts:
        concept_names = [c.name for c in conclusion.harvested_concepts]
        final_summary += i18n.get(
            "prompts.finish.brain_update",
            count=len(concept_names),
            concepts=', '.join(concept_names)
        )
    
    # Append todo notice if created
    if todo_notice:
        final_summary += todo_notice

    # 6. Sync Trace to Episode Graph
    try:
        from app.core.learning.trace_recorder import sync_thread_to_graph
        thread_id = config.get("configurable", {}).get("thread_id", None)

        if thread_id:
            logger.info(f"Syncing thread {thread_id} to Episode Graph...")
            
            # Extract goal from first HumanMessage
            first_goal = None
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    first_goal = get_message_text(msg)[:2000]
                    break
            
            # Extract concept names for linking
            concept_names = [c.name for c in conclusion.harvested_concepts] if conclusion.harvested_concepts else []
            
            await sync_thread_to_graph(
                thread_id=thread_id, 
                project_id=project_id,
                goal=first_goal,
                result_summary=conclusion.summary,
                concept_names=concept_names
            )
    except Exception as e:
        logger.error(f"Failed to sync episode to graph: {e}")

    # Return the summary as a regular AIMessage (will be logged by DatabaseCallbackHandler)
    # Note: Since this is manual AIMessage, it needs to be invoked via LLM for persistence
    # We'll create a simple pass-through for the summary
    
    # Use LLM to "echo" the summary so it gets captured by callback
    echo_llm = LLMFactory.create_llm(temperature=0)
    echo_prompt = f"Return the following text EXACTLY as-is, with no modifications:\n\n{final_summary}"
    
    try:
        final_response = await echo_llm.ainvoke(
            [SystemMessage(content=echo_prompt)],
            config=config
        )
    except Exception:
        # Fallback if echo fails
        final_response = AIMessage(content=final_summary)

    return {
        "messages": [final_response]
    }
