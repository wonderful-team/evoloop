import logging

from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.domain.memory.service import memory_service
from app.domain.tools.learner import ExtractionResult, harvest_knowledge

logger = logging.getLogger(__name__)

async def finish_node(state: AgentState, config: RunnableConfig):
    """
    Finalize the workflow.
    Automatically harvests knowledge from:
    1. Code Changes (if any)
    2. Deep Research Reports (if any)
    """
    logger.info("Nodes: Finish - Finalizing and Harvesting Knowledge")

    # 1. Harvest Code Changes
    # Only if we suspect code was modified.
    # We check if there are any tool calls related to file modification in history.
    has_code_changes = False

    # Expanded file operation keywords to detect code changes
    CODE_CHANGE_KEYWORDS = [
        "write_file", "replace_file", "edit_file",
        "create_file", "delete_file", "patch_file",
        "save_file", "update_file", "modify_file",
        "git_commit", "apply_diff", "insert_code"
    ]

    # Check recent tool history in state
    tool_history = state.get("tool_history", [])
    for sig in tool_history:
        sig_lower = sig.lower() if sig else ""
        if any(kw in sig_lower for kw in CODE_CHANGE_KEYWORDS):
            has_code_changes = True
            break

    # Track harvested items for the summary
    harvested_concepts = []

    if has_code_changes:
        logger.info("Detected code changes. Attempting to harvest knowledge...")
        try:
            # We use a lower-level invocation or parse specific output if possible
            # But the tool returns a string. We might need to refactor learner to return struct if we want structured summary here.
            # For now, we trust the logs or just generic message.
            # actually, let's just run it.
            result_str = await harvest_knowledge.ainvoke({"lookback": 1}, config=config)

            # Simple parse to display
            if "Harvested Concepts:" in result_str:
                 lines = result_str.split('\n')
                 for line in lines:
                     if line.strip().startswith("- "):
                         harvested_concepts.append(line.strip()[2:])

        except Exception as e:
            logger.warning(f"Auto-harvest code failed: {e}")

    # 2. Harvest Research Report
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage):
        content = messages[-1].content
        if "Full Research Report" in content or "# Final Conclusion" in content:
            logger.info("Detected Research Report. Harvesting concepts from text...")
            new_concepts = await _harvest_report_concepts(content, state.get("project_id", 1))
            harvested_concepts.extend(new_concepts)



    # 0. Language Preference
    from app.domain.system.service import SystemConfigService
    user_lang = SystemConfigService.get_language_preference()

    is_cn = "Chinese" in user_lang or "zh" in user_lang.lower()

    # 3. Generate Final Debrief
    title = "✅ **Task Completed**" if not is_cn else "✅ **任务已完成**"
    harvest_title = "\n🧠 **Brain Update (Knowledge Harvested):**" if not is_cn else "\n🧠 **大脑更新 (知识收割):**"
    footer = "\nI have recorded these insights to my long-term memory for future use." if not is_cn else "\n我已经将这些见解记录到长期记忆中，供未来使用。"

    summary_parts = [title]

    if harvested_concepts:
        unique_concepts = list(set(harvested_concepts))
        summary_parts.append(harvest_title)
        for c in unique_concepts:
             summary_parts.append(f"- {c}")

    if has_code_changes or harvested_concepts:
        summary_parts.append(footer)
    else:
        pass

    final_msg = "\n".join(summary_parts)

    # 4. Proactive Todo Check (The "Meeting Minutes" Strategy)
    try:
        todo_notice = await _check_proactive_todos(state, config)
        if todo_notice:
            final_msg += f"\n\n{todo_notice}"
    except Exception as e:
        logger.warning(f"Proactive todo check failed: {e}")

    # 5. Sync Trace to Episode Graph (Graph Memory)
    try:
        from app.core.learning.trace_recorder import sync_thread_to_graph
        thread_id = config.get("configurable", {}).get("thread_id", None)
        project_id = state.get("project_id", 1)

        if thread_id:
             logger.info(f"Syncing thread {thread_id} to Episode Graph...")
             await sync_thread_to_graph(thread_id, project_id)
        else:
             logger.warning("No thread_id found in config, skipping Episode Sync.")
    except Exception as e:
        logger.error(f"Failed to sync episode to graph: {e}")

    return {
        "messages": [AIMessage(content=final_msg)]
    }

async def _check_proactive_todos(state: AgentState, config: RunnableConfig) -> str | None:
    """
    Analyze the conversation to see if any todos should be created proactively.
    Acts like a "Meeting Minutes" summarizer.
    """
    messages = state.get("messages", [])
    if not messages: return None

    # Heuristic Check: Removed per user feedback.
    # We now trust the LLM to analyze the context directly for every finish state.
    # This ensures we catch implied tasks in any language without hardcoded keywords.
    content_blob = "\n".join([m.content for m in messages[-5:] if isinstance(m, (HumanMessage, AIMessage))])

    # LLM Analysis
    try:
        from app.domain.tools.manage_todo import manage_todo
        from langchain_core.pydantic_v1 import BaseModel, Field

        class ProactiveTodo(BaseModel):
            should_create: bool = Field(description="Whether a todo should be created.")
            title: str | None = Field(description="Title of the todo.")
            due_date: str | None = Field(description="Due date in relative format (e.g. '1 hour') or ISO.")
            reason: str | None = Field(description="Why this todo is needed.")

        llm = LLMFactory.create_llm(temperature=0)
        structured = llm.with_structured_output(ProactiveTodo)
        
        system_prompt = """You are a Proactive Assistant. 
Analyze the recent conversation. Did the user or agent mention a task that needs to be done LATER, or is currently running and needs checking?
Examples: "I'm deploying...", "Run tests (takes 30m)", "Remind me to check logs".
Ignore if:
1. The task is already completed.
2. It's just a general statement or chitchat (e.g. "Thanks", "Goodbye").
3. The user explicitly said they will handle it themselves without needing a reminder.

If yes, extract the todo details. due_date should be relative (e.g. '30 mins') if implied."""

        result = await structured.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Conversation History:\n{content_blob}")
        ])
        
        if result and result.should_create and result.title:
            logger.info(f"Proactive Todo Identified: {result.title} ({result.due_date})")
            
            # Execute Tool
            # We must use .ainvoke because it is a StructuredTool
            response = await manage_todo.ainvoke(
                {
                    "action": "add",
                    "title": result.title,
                    "due_date": result.due_date,
                    "category": "proactive",
                    "priority": "medium",
                    "description": f"Auto-created from context: {result.reason}"
                },
                config=config 
            )
            
            return f"📝 **Proactive Reminder**: I've added a todo: '{result.title}' ({result.due_date or 'No date'})."
            
    except Exception as e:
        logger.warning(f"Error in proactive todo analysis: {e}")
    
    return None

async def _harvest_report_concepts(report_text: str, project_id: int) -> list[str]:
    """
    Extract concepts from a text report. Returns list of concept names.
    """
    harvested = []
    try:
        if len(report_text) > 15000:
            report_text = report_text[:15000] + "..."

        llm = LLMFactory.create_llm()
        structured_llm = llm.with_structured_output(ExtractionResult)

        prompt = f"""You are a Knowledge Engineer.
        Extract "Domain Concepts", "Architecture Decisions", or "Key Findings" from the following Research Report.
        
        Report:
        {report_text}
        
        Extract up to 5 most important concepts worth remembering for this project.
        """

        result = await structured_llm.ainvoke([SystemMessage(content=prompt)], config={"callbacks": []})

        if result and result.concepts:
            for concept in result.concepts:
                await memory_service.add_concept(
                    name=concept.name,
                    description=concept.description,
                    project_id=project_id,
                    related_files=[]
                )
                harvested.append(concept.name)
            logger.info(f"Harvested {len(result.concepts)} concepts from report.")

    except Exception as e:
        logger.error(f"Failed to harvest report: {e}")

    return harvested
