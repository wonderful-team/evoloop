from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.workflows.state import AgentState
from app.domain.research.engine import DeepResearchEngine
from app.core.config import settings
from app.logging import logger
from app.core.llm.factory import LLMFactory


async def deep_researcher_node(state: AgentState, config: RunnableConfig):
    """
    Deep Research Node.
    Delegates to the DeepResearchEngine.
    """
    llm = LLMFactory.create_llm()
    engine = DeepResearchEngine(llm)

    messages = state.get("messages", [])

    # Initialize state variables if missing
    topic = state.get("research_topic", "")
    max_iter = state.get("max_research_iterations", settings.RESEARCH_MAX_ITERATIONS)

    # Determine Topic
    # Determine Topic
    if not topic:
        # In parallel mode, topic MUST be passed. 
        # Fallback to last message is dangerous if running multiple instances.
        return {
            "messages": [AIMessage(content="Error: No research topic provided.")],
            "next_node": "supervisor"
        }

    logger.info(f"DeepResearcher Node running for topic: {topic}")

    try:
        # Run the engine
        # The engine manages the full loop (Plan -> Iterate -> Conclude)
        # and returns the final markdown report.
        final_report = await engine.run(topic, max_iterations=max_iter, config=config)

        # In this simplified integration, we consider the process atomic from the graph's perspective.
        # We don't expose intermediate steps to the graph unless we refactor Engine to be a generator.
        # For now, we return the final result.

        return {
            "messages": [AIMessage(content=final_report)],
            "research_logs": [f"Full Research Report:\n{final_report}"],  # Simplified logging for state compatibility
            "research_loop_count": max_iter,  # Mark as done
            "next_node": "supervisor"
        }
    except Exception as e:
        logger.error(f"Deep Research Failed: {e}")
        return {
            "messages": [AIMessage(content=f"Error during deep research: {e}")],
            "next_node": "supervisor"
        }
