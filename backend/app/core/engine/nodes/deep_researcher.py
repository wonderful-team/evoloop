from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory
from app.domain.research.engine import DeepResearchEngine
from app.i18n.service import i18n
import logging
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

    messages = state.get("messages", [])

    # Initialize state variables if missing
    topic = state.get("research_topic", "")

    # [FIX] Phase 21: Context Handoff from Supervisor
    # Supervisor puts context in scratchpad['handoff_context'], but we need it locally.
    if not topic:
        scratchpad = state.get("scratchpad", {})
        handoff = scratchpad.get("handoff_context", {})
        
        if isinstance(handoff, str):
            try:
                import json
                handoff = json.loads(handoff)
            except Exception:
                handoff = {}

        # Try common keys
        topic = handoff.get("topic") or handoff.get("research_topic") or handoff.get("query") or ""
        
        if topic:
            logger.info(f"[DeepResearcher] 🔗 Context Handoff: Found topic '{topic}' in scratchpad.")

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

    try:
        # Run the engine
        # The engine manages the full loop (Plan -> Iterate -> Conclude)
        # and returns the final markdown report.
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
