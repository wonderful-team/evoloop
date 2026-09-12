import logging

from app.core.context.manager import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.domain.planning.constants import (
    RETRIEVAL_LIMIT,
    TREE_FILE_LIMIT,
    TREE_MAX_DEPTH,
)

from ...constants import DEFAULT_PROJECT_ID
from ...utils.template import render_template

logger = logging.getLogger(__name__)




@evoloop_tool(
    summary_template="evoloop.tool_summary.analyze_feasibility",
)
async def analyze_feasibility(proposed_plan: str, config: RunnableConfig) -> str:
    """
    Analyze the technical feasibility of a proposed development plan.
    It retrieves relevant code context and checks for potential issues like hallucinations or breaking changes.
    Args:
        proposed_plan: The detailed plan step-by-step.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id if ctx.project_id is not None else DEFAULT_PROJECT_ID
    root = ctx.working_directory or "."

    try:
        from app.domain.codebase.retrieval.service import RetrievalService
        from app.infrastructure.config.service import SystemConfigService
        from app.infrastructure.llm.factory import LLMFactory
        from app.infrastructure.schemas import LLMConfig

        # Retrieval
        retrieval_service = RetrievalService()
        search_results = await retrieval_service.search(
            proposed_plan, operator="or", project_id=project_id, limit=RETRIEVAL_LIMIT
        )

        context_str = "\n".join(
            [
                f"File: {r['file_path']}\nSnippet: {r['content'][:500]}..."
                for r in search_results
            ]
        )

        # Get Project Structure
        # Use underlying Generator directly (no longer a tool)
        from app.core.project.tree_generator import AnnotatedTreeGenerator

        # Smart Truncation enabled to avoid context overflow
        generator = AnnotatedTreeGenerator(
            root,
            max_depth=TREE_MAX_DEPTH,
            with_symbols=False,
            file_limit=TREE_FILE_LIMIT,
        )
        tree = await generator.generate()

        # LLM Analysis
        llm = await LLMFactory.create_llm(LLMConfig(model_name=""))
        user_lang = SystemConfigService.get_language_preference()

        prompt_text = render_template(
            "domain/planning/feasibility_analysis.prompt.j2",
            plan=proposed_plan,
            context=context_str,
            tree=tree,
            user_lang=user_lang,
        )

        # Use simple invoke with prepared text
        response = await llm.ainvoke(prompt_text, config=config)
        report = response.content

        return report

    except Exception as e:
        logger.exception(f"Feasibility analysis failed: {e}")
        return f"Analysis Failed: {str(e)}"
