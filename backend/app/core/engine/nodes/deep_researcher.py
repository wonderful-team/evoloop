import logging

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine import AgentState
from app.core.llm.factory import LLMFactory
from app.domain.research.engine import DeepResearchEngine
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


async def deep_researcher_node(state: AgentState, config: RunnableConfig):
    """
    Deep Research Node.
    Delegates to the DeepResearchEngine.
    """
    llm = LLMFactory.create_llm()
    # Researcher Engine usually manages its own tools, but we should enforce it uses RBAC tools
    from app.core.tools.registry_utils import get_node_tools

    tools = get_node_tools("researcher")
    # engine = DeepResearchEngine(llm) -> We need to check if Engine supports tools injection.
    # Assuming DeepResearchEngine has its own internal tool logic or accepts tools.
    # If not, we might need to modify DeepResearchEngine.
    # For now, let's assume it has internal logic as it wasn't passing tools before.
    # BUT wait, the proposal says Researcher gets `fs_read`.
    # Let's keep it as is for now but if we need to restrict, we'd pass tools here.
    # Since DeepResearchEngine likely instantiates its own tools internally (like web search),
    # we might need to refactor DeepResearchEngine later.
    # For this task, we will just proceed with others as DeepResearcher logic is encapsulated.
    # Pass specific tools to engine
    engine = DeepResearchEngine(llm, tools=tools)

    topic = state.get("research_topic", "")
    execution_ticket = state.get("execution_ticket")
    
    # 1. Blackboard Context Handoff (v3.2)
    if execution_ticket:
        logger.info("[DeepResearcher] 🎫 Ticket Match - Enabling Blackboard Isolation")
        topic = execution_ticket.get("topic") or execution_ticket.get("parameters", {}).get("topic")
        
        # Isolation: prune history
        criteria = "\n".join([f"- {c}" for c in execution_ticket.get("acceptance_criteria", [])])
        isolated_msg = f"### RESEARCH MISSION\nTopic: {topic}\n\nAcceptance Criteria:\n{criteria}\n\nPlease proceed with deep research."
        messages = [HumanMessage(content=isolated_msg)]
    else:
        # Fallback to legacy context handoff
        messages = list(state.get("messages", []))
        if not topic:
            scratchpad = state.get("scratchpad", {})
            handoff = scratchpad.get("handoff_context", {})
            # ... (rest of old logic for compatibility)
            if isinstance(handoff, str):
                try:
                    import json
                    handoff = json.loads(handoff)
                except Exception:
                    handoff = {}
            topic = handoff.get("topic") or handoff.get("research_topic") or handoff.get("query") or ""

    max_iter = state.get("max_research_iterations", settings.RESEARCH_MAX_ITERATIONS)

    # Determine Topic
    if not topic:
        # In parallel mode, topic MUST be passed.
        # Fallback to last message is dangerous if running multiple instances.
        return {
            "messages": [AIMessage(content=i18n.get("prompts.deep_research.error_no_topic"))],
            "next_node": "supervisor"
        }

    logger.info(f"DeepResearcher Node running for topic: {topic}")

    # Skills as Knowledge Injection
    skills = []
    try:
        from app.core.learning.discovery import skill_discovery
        skills = await skill_discovery.retrieve(topic, top_k=3)
        if skills:
            logger.info(f"[DeepResearcher] 📖 Found {len(skills)} relevant skills for knowledge injection")
    except Exception as e:
        logger.warning(f"[DeepResearcher] Skill retrieval failed: {e}")

    try:
        # Run the engine
        # Pass skills to engine if it supports prompt builders internally (e.g. for sub-tasks)
        # or combine with isolated message.
        if skills:
            from app.core.prompts.developer_builder import DeveloperPromptBuilder
            # We can use a helper or builder to format these for the engine's internal planning
            skill_knowledge = "\n".join([f"### 📘 Skill: {s.name}\n{s.instructions}" for s in skills])
            topic = f"{topic}\n\n### EXPERT KNOWLEDGE (SOPs)\n{skill_knowledge}"

        final_report = await engine.run(topic, previous_history=messages, max_iterations=max_iter, config=config)

        # In this simplified integration, we consider the process atomic from the graph's perspective.
        # We don't expose intermediate steps to the graph unless we refactor Engine to be a generator.
        # For now, we return the final result.

        return {
            "messages": [AIMessage(content=final_report)],
            "research_logs": [f"Full Research Report:\n{final_report}"],  # Simplified logging for state compatibility
            "research_loop_count": max_iter,  # Mark as done
            "next_node": "supervisor",
        }
    except Exception as e:
        logger.error(f"Deep Research Failed: {e}")
        return {
            "messages": [AIMessage(content=i18n.get("prompts.deep_research.error_failed", error=str(e)))],
            "next_node": "supervisor"
        }
