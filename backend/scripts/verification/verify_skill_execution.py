import asyncio
import json
import logging
import os
import sys
from datetime import datetime

# Add project root to path
# Add project root to path (backend/)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.workflows.nodes.supervisor import supervisor_node
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import LearnedSkill

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Starting Skill Execution Verification...")

    # 1. Setup Database
    async with session_scope() as db:
        # Create a test skill
        skill_name = "verify_test_read_file"

        # Check if exists and delete
        from sqlalchemy import delete
        stmt = delete(LearnedSkill).where(LearnedSkill.name == skill_name)
        await db.execute(stmt)
        await db.commit()

        # Insert new skill
        test_skill = LearnedSkill(
            name=skill_name,
            description="Reads a file from the system",
            trigger_patterns=json.dumps(["read file {filename}", "cat {filename}"]),
            parameters=json.dumps([{
                "name": "filename",
                "type": "string",
                "description": "Path to file",
                "required": True
            }]),
            steps=json.dumps([{
                "action": "manage_file",
                "args": {"action": "read", "path": "{{filename}}"}
            }]),
            tools_used=json.dumps(["manage_file"]),
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(test_skill)
        await db.commit()
        await db.refresh(test_skill)
        logger.info(f"✅ Created test skill: {test_skill.name} (ID: {test_skill.id})")

    # 2. Simulate User Request
    # We want to read THIS file (verify_skill_execution.py)
    target_file = "verify_skill_execution.py"
    user_msg = HumanMessage(content=f"read file {target_file}")

    state = {
        "messages": [user_msg],
        "project_id": 1,
        "skill_execution_attempted": False
    }

    config = RunnableConfig(
        configurable={"thread_id": "verify_test", "working_directory": os.getcwd()}
    )

    logger.info(f"🤖 Invoking Supervisor with input: '{user_msg.content}'")

    # 3. Call Supervisor Node
    try:
        result = await supervisor_node(state, config)

        # 4. Verify Result
        logger.info("✅ Supervisor returned result")

        # Check next node
        if result.get("next_node") == "finish":
            logger.info("✅ Next node is 'finish' (Correct)")
        else:
            logger.error(f"❌ Next node is '{result.get('next_node')}', expected 'finish'")
            return

        # Check messages
        messages = result.get("messages", [])
        if not messages:
            logger.error("❌ No messages returned")
            return

        last_msg = messages[-1]
        if isinstance(last_msg, AIMessage):
            content = last_msg.content
            logger.info(f"📄 Response Content:\n{content[:200]}...")

            if "Executed skill" in content and "Starting Skill Execution Verification" in content:
                logger.info("✅ Skill executed successfully and read the file content!")
            else:
                logger.error("❌ Response does not contain expected file content or success message")
        else:
            logger.error("❌ Last message is not AIMessage")

        # Check execution flag
        if result.get("skill_execution_attempted"):
            logger.info("✅ skill_execution_attempted flag is True")
        else:
            logger.warning("⚠️ skill_execution_attempted flag missing or False")

    except Exception as e:
        logger.error(f"❌ Execution failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
