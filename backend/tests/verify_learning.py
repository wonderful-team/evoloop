import asyncio
import json
import logging
import os
import sys
import uuid

# Add backend to path
sys.path.append(os.getcwd())

from app.core.learning.trace_recorder import TraceCallbackHandler
from app.domain.learning.tools import learn_skill_from_trace
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import LearnedSkill, TraceEvent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_learning")

async def test_learning_loop():
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"
    logger.info(f"--- Starting Learning Verification for Thread: {thread_id} ---")

    # 1. Simulate Agent Execution (Trace Recording)
    # We manually invoke the handler as if the AgentEngine was running
    handler = TraceCallbackHandler(thread_id=thread_id)

    logger.info("1. simulating: Agent enters 'coder' node...")
    await handler.on_chain_start(
        serialized={"id": ["app", "nodes", "coder"]},
        inputs={"messages": []},
        metadata={"langgraph_node": "coder"}
    )

    logger.info("2. simulating: Agent calls 'manage_file' (Trial 1 - Write)...")
    await handler.on_tool_start(
        serialized={"name": "manage_file"},
        input_str=json.dumps({"action": "write", "path": "/tmp/hello.py", "content": "print('hello')"}),
    )
    # Simulate tool output (Environment feedback)
    # Note: on_tool_end currently doesn't link to the start in the naive handler,
    # but the synthesizer looks for tool_call events primarily.

    logger.info("3. simulating: Agent calls 'run_command' (Trial 1 - Run)...")
    await handler.on_tool_start(
        serialized={"name": "run_command"},
        input_str=json.dumps({"command": "python /tmp/hello.py"}),
    )

    # 2. Verify Traces in DB
    async with session_scope() as db:
        from sqlalchemy import func, select
        stmt = select(func.count()).where(TraceEvent.thread_id == thread_id)
        count = (await db.execute(stmt)).scalar()
        logger.info(f"-> Verified {count} trace events recorded in DB.")
        assert count >= 2, "Failed to record traces!"

    # 3. Trigger Synthesis (The 'Skill Acquisition' Step)
    logger.info("4. Triggering Skill Synthesis...")
    # Invoke the tool via LangChain interface
    result = await learn_skill_from_trace.ainvoke({"thread_id": thread_id})
    logger.info(f"-> Synthesis Result:\n{result}")

    # 4. Verify Learned Skill
    async with session_scope() as db:
        from sqlalchemy import select
        stmt = select(LearnedSkill).where(LearnedSkill.source_thread_id == thread_id)
        skill = (await db.execute(stmt)).scalar_one_or_none()

        if skill:
            logger.info(f"✅ SUCCESS: Skill '{skill.name}' learned!")
            logger.info(f"   Triggers: {skill.trigger_patterns}")
            logger.info(f"   Tools Used: {skill.tools_used}")
        else:
            logger.error("❌ FAILED: No skill created in DB.")

if __name__ == "__main__":
    asyncio.run(test_learning_loop())
