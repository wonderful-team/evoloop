import logging
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.core.workflows.state import AgentState
from app.core.llm.factory import LLMFactory
from app.domain.tools.learner import harvest_knowledge, ExtractionResult
from app.domain.memory.service import memory_service
from app.core.config import settings

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
    
    # Simple heuristic: check recent tool history in state
    tool_history = state.get("tool_history", [])
    for sig in tool_history:
        if "write_file" in sig or "replace_file" in sig or "edit_file" in sig:
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
    
    # 4. Sync Trace to Episode Graph (Graph Memory)
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
