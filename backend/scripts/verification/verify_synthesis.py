import asyncio
import json
import logging
import os
import sys
import uuid

# Ensure backend modules are efficient
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from datetime import datetime

from app.core.learning.skill_synthesizer import EnhancedWorkflowSynthesizer
from app.infrastructure.database.sql.database import session_scope
from app.models import LearnedSkill, TraceEvent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_synthesis")

async def verify_synthesis():
    thread_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    logger.info(f"Starting verification with Thread ID: {thread_id}")

    # 1. Simulate Recording a Trace (User searches for a file and reads it)
    events = [
        {
            "step": 1,
            "type": "input",
            "payload": {"value": "search for verify_synthesis.py"},
            "ui": {"selector": "#chat-input", "text": ""}
        },
        {
            "step": 2,
            "type": "click",
            "payload": {"x": 100, "y": 200},
            "ui": {"selector": ".submit-btn", "text": "Send"}
        },
        # Agent response (simulated)
        {
            "step": 3,
            "type": "tool_call",
            "payload": {"name": "search_codebase", "args": {"query": "verify_synthesis.py"}},
            "is_human": False
        },
        # User feedback/next action
        {
            "step": 4,
            "type": "input",
            "payload": {"value": "good, now read it"},
            "ui": {"selector": "#chat-input", "text": ""},
            "is_human": True
        }
    ]

    logger.info("Inserting mock trace events...")
    async with session_scope() as db:
        for ev in events:
            db_event = TraceEvent(
                thread_id=thread_id,
                recording_session_id=session_id,
                step_number=ev["step"],
                node_name="user_interaction" if ev.get("is_human", True) else "agent_node",
                action_type=ev["type"],
                action_payload=json.dumps(ev["payload"]),
                is_human_action=ev.get("is_human", True),
                state_snapshot="{}"
            )
            db_event.created_at = datetime.utcnow()
            db.add(db_event)
        await db.commit()

    # 2. Run Synthesis
    logger.info("Running Workflow Synthesizer...")
    try:
        synthesizer = EnhancedWorkflowSynthesizer(thread_id, session_id)
        skill = await synthesizer.synthesize()

        logger.info("✅ Synthesis Successful!")
        logger.info(f"Skill Name: {skill.name}")
        logger.info(f"Description: {skill.description}")
        logger.info(f"Parameters: {[p.name for p in skill.parameters]}")
        logger.info(f"Steps: {len(skill.steps)}")
        logger.info(f"YAML:\n{skill.to_yaml()}")

        # 3. Save to verify Persistence (simulating API)
        logger.info("Saving skill to DB manually to verify model...")
        async with session_scope() as db:
            db_skill = LearnedSkill(
                name=skill.name,
                description=skill.description,
                trigger_patterns=json.dumps(skill.trigger_patterns),
                parameters=json.dumps([p.__dict__ for p in skill.parameters]),
                preconditions=json.dumps(skill.preconditions),
                steps=json.dumps([s.__dict__ for s in skill.steps]),
                tools_used=json.dumps(skill.tools_used),
                source_thread_id=skill.source_thread_id,
                source_session_id=skill.source_session_id
            )
            db.add(db_skill)
            await db.commit()
            logger.info("✅ Skill Saved Successfully")

            # Clean up
            await db.delete(db_skill)

            # Cleanup events
            # (Simplified cleanup)
            pass

    except Exception as e:
        logger.error(f"❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_synthesis())
