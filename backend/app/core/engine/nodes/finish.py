import logging
import os
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.core.engine.message_utils import get_message_text, smart_window_slice
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class HarvestedConcept(BaseModel):
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of what it is and how it was used")


class ProactiveTodo(BaseModel):
    should_create: bool = Field(description="Whether a todo should be created")
    title: str | None = Field(description="Title of the todo")
    due_date: str | None = Field(description="Due date in relative format (e.g. '1 hour') or ISO")
    reason: str | None = Field(description="Why this todo is needed")


from typing import Any
try:
    from pydantic import field_validator
except ImportError:
    from pydantic import validator as field_validator

class SessionConclusion(BaseModel):
    """Unified output for finish node - combines summary, knowledge harvesting, and todo detection."""
    summary: str = Field(description="Human-readable summary of what was accomplished in this session")
    harvested_concepts: list[HarvestedConcept] = Field(
        default_factory=list,
        description="Key concepts, patterns, or decisions worth remembering for future tasks",
    )
    proactive_todo: ProactiveTodo | None = Field(
        default=None,
        description="A todo item if any follow-up action was mentioned"
    )

    @field_validator("proactive_todo", mode="before")
    @classmethod
    def parse_proactive_todo(cls, v: Any) -> Any:
        # Robustly handle JSON strings if passed by LLM instead of object
        if isinstance(v, str):
            try:
                import json
                # If it's a string, try to decode it
                if v.strip().lower() == "null" or v.strip() == "":
                    return None
                return json.loads(v)
            except Exception:
                # If parsing fails, return None to be safe (or log warning)
                return None
        return v


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
    execution_ticket = state.get("execution_ticket")
    test_results = state.get("structured_test_results", {})

    # Pre-generate Message ID for consistency
    final_message_id = str(uuid.uuid4())

    # Language preference
    from app.core.system import SystemConfigService

    user_lang = SystemConfigService.get_language_preference()

    # 2. Build Context Summary
    recent_history = smart_window_slice(messages, window_size=15)

    # Tool history summary (for context enrichment)
    tool_summary = "None"
    if tool_history:
        # Extract unique tool names for summary
        unique_tools = list({sig.split(":")[0] for sig in tool_history if ":" in sig})
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
                timeout=5,
            )
            if result.stdout.strip():
                git_context = f"\n**Git Changes (Uncommitted):**\n```\n{result.stdout[:500]}\n```"
        except Exception:
            pass

    # 3. Unified Prompt
    from app.core.prompts.finish import FinishPromptBuilder

    builder = FinishPromptBuilder(
        user_lang=user_lang,
        current_plan=current_plan,
        tool_summary=tool_summary,
        execution_ticket=execution_ticket,
        test_results=test_results,
        git_context=git_context
    )
    conclusion_prompt = builder.build()

    # 4. Single LLM Call with Structured Output
    llm = LLMFactory.create_llm(temperature=0.3)
    structured_llm = llm.with_structured_output(SessionConclusion)

    messages_for_analysis = [SystemMessage(content=conclusion_prompt)] + recent_history

    try:
        conclusion = await structured_llm.ainvoke(messages_for_analysis, config={"callbacks": []})
    except Exception as e:
        logger.error(f"Failed to generate SessionConclusion: {e}")
        # Fallback to simple response
        return {"messages": [AIMessage(content="✅ Task completed.")]}

    if not conclusion:
        logger.warning("LLM returned None for SessionConclusion")
        return {"messages": [AIMessage(content="✅ Task completed.")]}

    # 5. Process Results

    # 5a. Dispatch Concept Harvesting (Async)
    if conclusion.harvested_concepts:
        try:
            from app.core.engine.tasks import harvest_concepts_task
            
            # Convert Pydantic to dict for Celery serialization
            concepts_data = [
                {"name": c.name, "description": c.description} 
                for c in conclusion.harvested_concepts
            ]
            
            harvest_concepts_task.delay(
                concepts_data=concepts_data, 
                project_id=project_id
            )
            logger.info(f"Dispatched harvest task for {len(concepts_data)} concepts")
        except Exception as e:
            logger.warning(f"Failed to dispatch harvest task: {e}")

    # 5b. Create proactive todo if needed (Keep Sync for UI Feedback)
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
                    "description": f"Auto-created: {conclusion.proactive_todo.reason}",
                },
                config={**config, "metadata": {**config.get("metadata", {}), "message_id": final_message_id}},
            )
            todo_notice = i18n.get(
                "prompts.finish.proactive_reminder",
                title=conclusion.proactive_todo.title,
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
            concepts=", ".join(concept_names),
        )

    # Append todo notice if created
    if todo_notice:
        final_summary += todo_notice

    # 6. Sync Trace to Episode Graph (Async)
    try:
        from app.core.engine.tasks import record_episode_task

        thread_id = config.get("configurable", {}).get("thread_id", None)

        if thread_id:
            # Extract goal from first HumanMessage (can be done here or in task, but passing clear args is safer)
            first_goal = None
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    first_goal = get_message_text(msg)[:2000]
                    break

            # Extract concept names
            concept_names = [c.name for c in conclusion.harvested_concepts] if conclusion.harvested_concepts else []

            record_episode_task.delay(
                thread_id=thread_id,
                project_id=project_id,
                goal=first_goal,
                result_summary=conclusion.summary,
                concept_names=concept_names,
                source_message_id=final_message_id,
            )
            logger.info(f"Dispatched episode record task for {thread_id}")
    except Exception as e:
        logger.error(f"Failed to sync episode to graph: {e}")

    # 7. Trigger Brain Memory Consolidation (Async Sleep Cycle)
    try:
        from app.core.brain.tasks import consolidate_memory
        
        logger.info(f"Dispatching Brain Consolidation Task (Async) for {final_message_id}...")
        consolidate_memory.delay(source_message_id=final_message_id)
        
    except Exception as e:
        logger.warning(f"Failed to dispatch Brain Consolidation: {e}")

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

    final_response.id = final_message_id
    return {"messages": [final_response]}
