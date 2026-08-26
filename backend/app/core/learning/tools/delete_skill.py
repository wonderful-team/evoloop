import logging

from app.core.learning.skills.discovery import skill_discovery
from app.core.learning.skills.lifecycle import delete_skill as delete_skill_record
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.delete_skill",
)
async def delete_skill(skill_id: int) -> str:
    """Physically delete a skill and its resources.

    Args:
        skill_id: The exact numerical ID of the skill (obtained from list_skills).
    """
    try:
        async with session_scope() as db:
            skill = await delete_skill_record(db, skill_id, member_id=0)
    except Exception as e:
        logger.exception(f"[delete_skill] Failed to delete skill {skill_id}: {e}")
        return ControllerResponse.error(
            f"Failed to delete skill {skill_id}", details=str(e)
        )

    try:
        from app.core.events.publishers import publish_skill_mutated

        await publish_skill_mutated(
            skill_id=skill_id,
            action="delete",
            namespace=skill.namespace,
            name=skill.name,
        )
        await skill_discovery.reload()
    except Exception as e:
        logger.warning(f"[delete_skill] publish/reload failed: {e}")

    return ControllerResponse.success(f"Skill {skill_id} deleted successfully.")
