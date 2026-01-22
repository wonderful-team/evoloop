import logging

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from app.core.engine.message_utils import get_message_text
from app.core.engine.state import AgentState
from app.core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


async def meta_reviewer_node(state: AgentState, config: RunnableConfig):
    """
    Meta-Reviewer Node: Analyzes repeated failures and advises the Supervisor.
    """
    llm = LLMFactory.create_llm(temperature=0.5)

    # 0. Language Preference handled by Builder now

    # 1. Get Architectural Context first (needed for builder)
    project_id = state.get("project_id", 1)
    plan = state.get("current_plan", "Unknown")
    test_results = state.get("test_results", "Unknown Failure")
    iteration_count = state.get("iteration_count", 0)

    import os

    from app.domain.visualizer.tree_generator import AnnotatedTreeGenerator

    # Resolve root
    root = config.get("configurable", {}).get("working_directory") or os.getcwd()

    try:
        # Depth 2 is usually enough for high-level architecture
        generator = AnnotatedTreeGenerator(root, max_depth=3, with_symbols=False, file_limit=30)
        tree_context = await generator.generate()
    except Exception as e:
        tree_context = f"Error fetching architecture: {e}"

    from app.core.prompts.meta_reviewer_builder import MetaReviewerPromptBuilder

    system_prompt_str = MetaReviewerPromptBuilder.build_system_prompt(
        project_id=project_id,
        plan=plan,
        test_results=test_results,
        iteration_count=iteration_count,
        tree=tree_context,
    )

    reviewer_prompt = ChatPromptTemplate.from_template(system_prompt_str)

    logger.info("Meta-Reviewer triggered.")

    # Chain no longer needs inputs as they are baked into prompt
    chain = reviewer_prompt | llm

    response = await chain.ainvoke({}, config=config)

    # will log it nicely, and we don't need manual persistence or manual prefixing.
    advice = get_message_text(response)

    return {
        "messages": [AIMessage(content=advice)],
        # We might want to reset iteration count or flag intervention,
        # but Supervisor logic handles the next step.
        # "technical_analysis": advice # Optionally update analysis
    }
