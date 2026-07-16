import logging

from app.core.events.publishers import publish_macro_mutated, publish_skill_mutated
from app.core.learning.skill_lifecycle import create_from_synthesis
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.tools import evoloop_tool
from app.i18n.service import i18n
from app.infrastructure.database import session_scope
from app.utils.parameters import normalize_parameters

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    required_benefit="skill_learning",
    summary_template="evoloop.tool_summary.learn_from_trace",
)
async def learn_from_trace(thread_id: str, session_id: str | None = None) -> str:
    """
    Analyzes the execution trace of a given thread/session and learns a reusable skill from it.
    This uses "Imitation Learning" to synthesize a parameterized skill configuration.

    Args:
        thread_id: The conversation thread ID to learn from.
        session_id: Optional session ID if specific session is targeted.
    """
    try:
        synthesizer = WorkflowSynthesizer(thread_id, session_id)
        result = await synthesizer.synthesize()
        skill_data = result.skill

        # Save to Database
        async with session_scope() as db:
            new_skill = await create_from_synthesis(
                db,
                name=skill_data.name,
                description=skill_data.description,
                trigger_patterns=skill_data.trigger_patterns,
                parameters=skill_data.parameters,
                preconditions=skill_data.preconditions,
                instructions=skill_data.instructions,
                tools_used=skill_data.tools_used,
                source_thread_id=skill_data.source_thread_id,
                source_session_id=skill_data.source_session_id,
            )
            new_macro = None
            if result.macro_script:
                from app.core.execution.macro.lifecycle import (
                    create_macro_from_synthesis,
                )

                new_macro = await create_macro_from_synthesis(
                    db,
                    name=new_skill.name,
                    description=new_skill.description,
                    trigger_patterns=new_skill.trigger_patterns,
                    parameters=normalize_parameters(new_skill.parameters),
                    macro_script=result.macro_script,
                    fallback_skill_id=new_skill.id,
                    source_thread_id=skill_data.source_thread_id,
                )
                new_skill.macro_id = new_macro.id
            # Commit happens automatically on exit of session_scope

        await publish_skill_mutated(skill_id=new_skill.id, action="create")
        if new_macro is not None:
            await publish_macro_mutated(new_macro.id, action="create")

        return i18n.get(
            "domain_tools.learning.success",
            name=new_skill.name,
            thread=thread_id,
            desc=skill_data.description,
            triggers=skill_data.trigger_patterns,
        )

    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.error(f"[learn_from_trace] Failed to learn from thread {thread_id}: {e}")
        return i18n.get("domain_tools.learning.failed", error=str(e))
