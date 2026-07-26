import logging
from typing import Annotated

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.engine.tasks import harvest_concepts_task
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.domain.tools.schemas import ExtractedConcept

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    is_hidden=True,  # Internal knowledge management, not user-facing
    summary_template="evoloop.tool_summary.save_concepts"
)
async def save_concepts(
    concepts: list[ExtractedConcept],
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Extracted important technical concepts, patterns, or architecture decisions
    from the current session and store them in the project's long-term memory.

    Args:
        concepts: A list of objects containing 'name' and 'description'.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id if ctx.project_id is not None else DEFAULT_PROJECT_ID

    if not concepts:
        return "No concepts provided for harvesting."

    try:
        # Normalize: LLM may pass dicts instead of ExtractedConcept objects
        normalized = []
        for c in concepts:
            if isinstance(c, dict):
                normalized.append({"name": c.get("name", ""), "description": c.get("description", "")})
            else:
                normalized.append({"name": c.name, "description": c.description})

        harvest_concepts_task.delay(concepts_data=normalized, project_id=project_id)
        names = [c["name"] for c in normalized]
        return f"Successfully dispatched harvesting task for {len(normalized)} concepts: {', '.join(names)}"

    except Exception:
        logger.exception("Failed to harvest knowledge")
        return "Error harvesting knowledge"
