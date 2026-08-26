import logging
from typing import Any

from app.core.learning.skills.discovery import skill_discovery
from app.core.learning.skills.lifecycle import update_skill as update_skill_record
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.update_skill",
)
async def update_skill(
    skill_id: int,
    name: str | None = None,
    description: str | None = None,
    namespace: str | None = None,
    instructions: str | None = None,
    trigger_patterns: list[str] | None = None,
    parameters: list[dict[str, Any]] | None = None,
) -> str:
    """Update a learned skill's definition (partial update).

    Args:
        skill_id: The exact numerical ID of the skill (obtained from list_skills).
        name: New skill name.
        description: New skill description.
        namespace: New namespace (e.g. 'domain/browser').
        instructions: New SOP instructions.
        trigger_patterns: New trigger patterns.
        parameters: New parameter definitions.
    """
    try:
        async with session_scope() as db:
            skill = await update_skill_record(
                db,
                skill_id,
                member_id=0,
                name=name,
                description=description,
                namespace=namespace,
                instructions=instructions,
                trigger_patterns=trigger_patterns,
                parameters=parameters,
            )
    except Exception as e:
        logger.exception(f"[update_skill] Failed to update skill {skill_id}: {e}")
        return ControllerResponse.error(
            f"Failed to update skill {skill_id}", details=str(e)
        )

    try:
        from app.core.events.publishers import publish_skill_mutated

        await publish_skill_mutated(skill_id=skill_id, action="update")
        await skill_discovery.reload()
    except Exception as e:
        logger.warning(f"[update_skill] publish/reload failed: {e}")

    return ControllerResponse.success(
        f"Skill {skill_id} ('{skill.name}') updated successfully."
    )
