import asyncio
import logging
import os
import sys
import uuid

# Ensure backend modules are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from datetime import datetime

from app.core.learning.workflow_synthesizer import (
    SynthesisMode,
    WorkflowSynthesizer,
)
from app.infrastructure.database import session_scope
from app.models import LearnedSkill, TraceEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_synthesis")


def _make_click_event(thread_id: str, step_number: int) -> TraceEvent:
    return TraceEvent(
        thread_id=thread_id,
        step_number=step_number,
        node_name="worker",
        event_type="click",
        payload={"selector": "#btn"},
        is_human_action=False,
        source="agent",
    )


def _make_input_event(thread_id: str, step_number: int) -> TraceEvent:
    return TraceEvent(
        thread_id=thread_id,
        step_number=step_number,
        node_name="user_interaction",
        event_type="input",
        payload={"selector": "#chat-input", "value": "hello"},
        is_human_action=True,
        source="human",
    )


async def _seed_trace(thread_id: str, session_id: str) -> None:
    async with session_scope() as db:
        for _i, event in enumerate(
            [
                _make_input_event(thread_id, 1),
                _make_click_event(thread_id, 2),
                _make_input_event(thread_id, 3),
            ],
            start=1,
        ):
            event.recording_session_id = session_id
            event.created_at = datetime.utcnow()
            db.add(event)


async def _cleanup(thread_id: str) -> None:
    async with session_scope() as db:
        await db.execute(
            TraceEvent.__table__.delete().where(TraceEvent.thread_id == thread_id)
        )
        await db.execute(
            LearnedSkill.__table__.delete().where(
                LearnedSkill.source_thread_id == thread_id
            )
        )


async def verify_synthesis():
    thread_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    logger.info(f"Starting verification with Thread ID: {thread_id}")

    await _seed_trace(thread_id, session_id)

    try:
        # 1. Skill mode
        logger.info("Running Workflow Synthesizer in SKILL mode...")
        synth = WorkflowSynthesizer(thread_id, session_id)
        result = await synth.synthesize()
        skill = result.skill
        if skill is None:
            raise ValueError("Skill mode did not produce a SynthesizedSkill")
        logger.info("✅ Skill synthesis successful")
        logger.info(f"Skill Name: {skill.name}")
        logger.info(f"Description: {skill.description}")
        logger.info(f"Parameters: {[p.name for p in skill.parameters]}")
        logger.info(f"YAML:\n{skill.to_yaml()}")

        # 2. Macro mode
        logger.info("Running Workflow Synthesizer in MACRO mode...")
        synth_macro = WorkflowSynthesizer(
            thread_id, session_id, macro_script="steps: []", mode=SynthesisMode.MACRO
        )
        macro_result = await synth_macro.synthesize()
        macro = macro_result.macro
        if macro is None:
            raise ValueError("Macro mode did not produce a SynthesizedMacro")
        logger.info("✅ Macro metadata synthesis successful")
        logger.info(f"Macro Name: {macro.name}")
        logger.info(f"Description: {macro.description}")
        logger.info(f"Namespace: {macro.namespace}")
        logger.info(f"YAML:\n{macro.to_yaml()}")

    finally:
        await _cleanup(thread_id)
        logger.info("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(verify_synthesis())
