import logging

from pydantic import Field
from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool
from app.infrastructure.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


class SynthesizeSkillInput(DynamicBaseModel):
    reason: str = Field(
        ...,
        description="Reason for triggering skill synthesis. Explain why this session is valuable (e.g., 'Successfully solved a complex bug', 'Implemented a new reusable component')."
    )
    thread_id: str | None = Field(
        None,
        description="The thread ID to synthesize. Defaults to current thread if not provided."
    )


@evoloop_tool(
    args_schema=SynthesizeSkillInput,
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.synthesize_skill"
)
async def synthesize_skill(reason: str, thread_id: str | None = None) -> str:
    """
    Manually trigger skill synthesis for the current or a specific thread.
    Use this when you have successfully completed a non-trivial task that 
    could be useful for future reference or tool creation.
    """
    ctx = ContextManager.current()
    target_thread = thread_id or (ctx.thread_id if ctx else None)
    project_id = ctx.project_id if ctx else DEFAULT_PROJECT_ID

    if not target_thread:
        return "Error: Could not determine thread_id for synthesis."

    logger.info(f"[Tool] Agent triggered manual skill synthesis for thread {target_thread}. Reason: {reason}")

    try:
        from app.infrastructure.queue.factory import get_scheduler

        # Trigger the recording task with auto_synthesize=True
        get_scheduler().send_task(
            "engine_record_episode",
            kwargs={
                "thread_id": target_thread,
                "project_id": project_id,
                "auto_synthesize": True
            },
            queue="default"
        )
        return f"Successfully triggered skill synthesis for thread {target_thread}. The system will now analyze the execution trace and synthesize new skills in the background."
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to trigger synthesis tool: {e}")
        return f"Error: Failed to dispatch synthesis task: {str(e)}"


class ReadSkillSopInput(DynamicBaseModel):
    skill_name: str = Field(
        ...,
        description="The exact name or the numeric ID of the skill/SOP to inspect."
    )


@evoloop_tool(
    args_schema=ReadSkillSopInput,
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.read_skill_sop"
)
async def read_skill_sop(skill_name: str) -> str:
    """
    Read the detailed markdown standard operating procedures (SOP) instructions for a specific skill by name or ID.
    Use this to dynamically inspect the exact steps of a matching skill.
    """
    try:
        async with session_scope() as session:
            stmt = select(LearnedSkill).where(
                LearnedSkill.is_active == True,
                (LearnedSkill.name == skill_name) | (LearnedSkill.id == int(skill_name) if skill_name.isdigit() else False)
            )
            result = await session.execute(stmt)
            skill = result.scalar_one_or_none()
            if not skill:
                return f"Skill or SOP '{skill_name}' not found."

            output = [
                f"# SOP: {skill.name}",
                f"**Description**: {skill.description}",
            ]
            if skill.resource_path:
                output.append(f"**Resource Path**: {skill.resource_path}")
            if skill.instructions:
                output.append("\n## Instructions:\n" + skill.instructions)
            else:
                output.append("\n*No instructions defined for this skill.*")
            return "\n".join(output)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to read skill SOP: {e}")
        return f"Error reading skill SOP: {str(e)}"


@evoloop_tool(
    is_state_mutating=False,
    summary_template="evoloop.tool_summary.list_skills"
)
async def list_skills() -> str:
    """
    List all available learned skills and standard operating procedures (SOPs) registered in the workspace system.
    Returns a lightweight summary of available skill names and descriptions.
    """
    try:
        async with session_scope() as session:
            stmt = select(LearnedSkill).where(LearnedSkill.is_active == True)
            result = await session.execute(stmt)
            skills = result.scalars().all()
            if not skills:
                return "No active skills or SOPs registered."

            lines = ["Available skills/SOPs:"]
            for s in skills:
                lines.append(f"- **{s.name}** (ID: {s.id}): {s.description}")
            return "\n".join(lines)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to list skills: {e}")
        return f"Error listing skills: {str(e)}"
