import asyncio
import json
import os
import sys
import uuid

from sqlalchemy import delete

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.learning.skill_executor import skill_matcher
from app.domain.learning.tools import learn_skill_from_trace
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models.learning import LearnedSkill, TraceEvent


async def test_skill_learning():
    print("\n--- Test: Skill Learning Pipeline ---")

    thread_id = f"test_thread_{uuid.uuid4().hex[:8]}"
    print(f"1. Creating Mock Trace for Thread: {thread_id}")

    # Simulate a "Check System Status" skill
    # User asks "check system", Agent runs "uptime" and "df -h"

    events = [
        # 1. User Input
        TraceEvent(
            thread_id=thread_id,
            step_number=1,
            node_name="user",
            action_type="user_input",
            action_payload=json.dumps({"content": "Check system health and disk space."}),
            is_human_action=True,
            state_snapshot="{}"
        ),
        # 2. Agent Action: Uptime
        TraceEvent(
            thread_id=thread_id,
            step_number=2,
            node_name="supervisor",
            action_type="tool_call",
            action_payload=json.dumps({"tool": "run_command", "args": {"command": "uptime"}}),
            is_human_action=False,
            state_snapshot="{}"
        ),
        # 3. Agent Action: Disk Space
        TraceEvent(
            thread_id=thread_id,
            step_number=3,
            node_name="supervisor",
            action_type="tool_call",
            action_payload=json.dumps({"tool": "run_command", "args": {"command": "df -h"}}),
            is_human_action=False,
            state_snapshot="{}"
        )
    ]

    async with session_scope() as db:
        for e in events:
            db.add(e)

    print("   Mock trace inserted.")

    # 2. Trigger Learning
    print("2. Triggering Skill Learning...")
    # learn_skill_from_trace is a StructuredTool, need to use ainvoke
    result = await learn_skill_from_trace.ainvoke({"thread_id": thread_id})
    print(f"   Tool Output:\n{result}")

    if "Failed" in result:
        print("❌ Learning Failed.")
        return

    # 3. Verify Database
    print("3. Verifying Database Storage...")
    async with session_scope() as db:
        from sqlalchemy import select
        stmt = select(LearnedSkill).where(LearnedSkill.source_thread_id == thread_id)
        skill = (await db.execute(stmt)).scalar_one_or_none()

        if skill:
            print(f"✅ Skill Found: {skill.name}")
            print(f"   Triggers: {skill.trigger_patterns}")
            print(f"   Steps: {skill.steps}")
        else:
            print("❌ Skill NOT found in DB.")
            return

    # 4. Verify Matching
    print("4. Verifying Skill Matcher...")
    # Force cache clear essentially
    skill_matcher._skills_cache = None

    match = await skill_matcher.match("can you check the system health?", threshold=0.4)
    if match and match.skill_id == skill.id:
        print(f"✅ Matcher Successful! Matched '{match.skill_name}' with confidence {match.confidence}")
    else:
        print(f"❌ Matcher Failed. Got: {match}")

    # Cleanup
    print("5. Cleanup...")
    async with session_scope() as db:
        await db.execute(delete(TraceEvent).where(TraceEvent.thread_id == thread_id))
        if skill:
            await db.execute(delete(LearnedSkill).where(LearnedSkill.id == skill.id))
    print("   Test Data Deleted.")

if __name__ == "__main__":
    asyncio.run(test_skill_learning())
