import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, Field

from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


class ConceptInput(BaseModel):
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of the concept")


@evoloop_tool
async def memorize_concepts(
    concepts: list[ConceptInput],
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Extracted important technical concepts, patterns, or architecture decisions 
    from the current session and store them in the project's long-term memory.
    
    Args:
        concepts: A list of objects containing 'name' and 'description'.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id or 1

    if not concepts:
        return "No concepts provided for harvesting."

    try:
        from app.core.engine.tasks import harvest_concepts_task

        # Convert to list of dicts for Celery
        concepts_data = [
            {"name": c.name, "description": c.description}
            for c in concepts
        ]

        # Trigger background task
        harvest_concepts_task.delay(
            concepts_data=concepts_data,
            project_id=project_id
        )

        names = [c.name for c in concepts]
        return f"Successfully dispatched harvesting task for {len(concepts)} concepts: {', '.join(names)}"

    except Exception as e:
        logger.error(f"Failed to harvest knowledge: {e}")
        return f"Error harvesting knowledge: {str(e)}"
