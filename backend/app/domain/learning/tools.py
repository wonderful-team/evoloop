import json

from app.core.learning.skill_synthesizer import EnhancedWorkflowSynthesizer
from app.core.tools.base import evoloop_tool
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models.learning import LearnedSkill


@evoloop_tool
async def learn_skill_from_trace(thread_id: str, session_id: str | None = None) -> str:
    """
    Analyzes the execution trace of a given thread/session and learns a reusable skill from it.
    This uses "Imitation Learning" to synthesize a parameterized skill configuration.
    
    Args:
        thread_id: The conversation thread ID to learn from.
        session_id: Optional session ID if specific session is targeted.
    """
    try:
        synthesizer = EnhancedWorkflowSynthesizer(thread_id, session_id)
        skill_data = await synthesizer.synthesize()

        # Save to Database
        async with session_scope() as db:
            # Check for name collision
            from sqlalchemy import select
            stmt = select(LearnedSkill).where(LearnedSkill.name == skill_data.name)
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if existing:
                # Update existing? Or error?
                # For now, let's append a suffix if needed or just update
                skill_data.name = f"{skill_data.name}_{int(time.time())}"

            new_skill = LearnedSkill(
                name=skill_data.name,
                description=skill_data.description,
                trigger_patterns=json.dumps(skill_data.trigger_patterns),
                parameters=json.dumps([p.__dict__ for p in skill_data.parameters]),
                preconditions=json.dumps(skill_data.preconditions),
                steps=json.dumps([s.__dict__ for s in skill_data.steps]),
                tools_used=json.dumps(skill_data.tools_used),
                source_thread_id=skill_data.source_thread_id,
                source_session_id=skill_data.source_session_id
            )
            db.add(new_skill)
            # Commit happens automatically on exit of session_scope

        return f"Successfully learned skill '{skill_data.name}' from thread {thread_id}.\nDescription: {skill_data.description}\nTriggers: {skill_data.trigger_patterns}"

    except Exception as e:
        return f"Failed to learn skill: {str(e)}"
