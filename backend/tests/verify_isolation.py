"""
Standalone script to verify multi-user data isolation.
Tests if user A can see user B's data through the API endpoints.
"""

import asyncio
import logging
from sqlmodel import Session

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_isolation")

# Setup environment to test mode
import os
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test_isolation.db"

from app.infrastructure.database.resource_manager import db_resource_manager
from app.models import Conversation, LearnedSkill
from app.core.memory.models import MemoryEntry, PrivacyLevel
from app.api.routes.conversations import list_conversations
from app.api.routes.learning import list_skills
from app.api.routes.memory import list_concepts
from app.models import User
from app.core.memory.manager import MemoryManager

async def setup_db():
    await db_resource_manager.initialize()
    # Initialize test DB
    
    # Clean previous data
    with Session(db_resource_manager.sync_engine) as session:
        session.query(Conversation).delete()
        session.query(LearnedSkill).delete()
        session.commit()

async def insert_dummy_data():
    with Session(db_resource_manager.sync_engine) as session:
        # Conversations
        session.add(Conversation(id="conv_101", title="User 101 Conv", member_id=101, project_id=1))
        session.add(Conversation(id="conv_102", title="User 102 Conv", member_id=102, project_id=1))
        session.add(Conversation(id="conv_0", title="Public Conv", member_id=0, project_id=1))
        
        # Skills
        session.add(LearnedSkill(id=101, name="Skill 101", member_id=101, is_active=True, project_id=1, description="", trigger_patterns=[], parameters=[]))
        session.add(LearnedSkill(id=102, name="Skill 102", member_id=102, is_active=True, project_id=1, description="", trigger_patterns=[], parameters=[]))
        session.add(LearnedSkill(id=100, name="Public Skill", member_id=0, is_active=True, project_id=1, description="", trigger_patterns=[], parameters=[]))
        
        session.commit()

async def verify_conversations():
    logger.info("=== Verifying Conversations ===")
    user_101 = User(id=101, is_active=True)
    user_102 = User(id=102, is_active=True)
    public_user = None
    
    res_101 = await list_conversations(current_user=user_101)
    res_102 = await list_conversations(current_user=user_102)
    res_public = await list_conversations(current_user=public_user)
    
    ids_101 = [c.thread_id for c in res_101.data]
    ids_102 = [c.thread_id for c in res_102.data]
    ids_public = [c.thread_id for c in res_public.data]
    
    logger.info(f"User 101 sees: {ids_101}")
    logger.info(f"User 102 sees: {ids_102}")
    logger.info(f"Public sees: {ids_public}")
    
    assert "conv_101" in ids_101 and "conv_102" not in ids_101, "User 101 can see User 102's data!"
    assert "conv_102" in ids_102 and "conv_101" not in ids_102, "User 102 can see User 101's data!"
    
    # In some designs, member_id=0 might be visible to all. But since filtering is exact match:
    # Actually, current implementation of list_conversations queries member_id == current_user.id
    # Let's see what it returns.

async def verify_skills():
    logger.info("=== Verifying Learned Skills ===")
    user_101 = User(id=101, is_active=True)
    user_102 = User(id=102, is_active=True)
    
    res_101 = await list_skills(active_only=False, page=1, page_size=50, current_user=user_101)
    res_102 = await list_skills(active_only=False, page=1, page_size=50, current_user=user_102)
    
    ids_101 = [s.id for s in res_101.data]
    ids_102 = [s.id for s in res_102.data]
    
    logger.info(f"User 101 sees: {ids_101}")
    logger.info(f"User 102 sees: {ids_102}")
    
    assert 101 in ids_101 and 102 not in ids_101, "User 101 can see User 102's skills!"
    assert 102 in ids_102 and 101 not in ids_102, "User 102 can see User 101's skills!"
    assert 100 not in ids_101 and 100 not in ids_102, "User 101 can see public skills (assuming exact match filter)"

async def verify_memory():
    logger.info("=== Verifying Memory Concepts ===")
    user_101 = User(id=101, is_active=True)
    
    manager = MemoryManager()
    await manager.initialize()
    
    # Store concept as 101
    await manager.store_concept(concept="Concept101", description="desc 101", project_id=1, member_id=101)
    # Store concept as 102
    await manager.store_concept(concept="Concept102", description="desc 102", project_id=1, member_id=102)
    
    res_101 = await list_concepts(project_id=1, manager=manager, current_user=user_101)
    res_102 = await list_concepts(project_id=1, manager=manager, current_user=User(id=102, is_active=True))
    
    names_101 = [c.name for c in res_101]
    names_102 = [c.name for c in res_102]
    
    logger.info(f"User 101 sees concepts: {names_101}")
    logger.info(f"User 102 sees concepts: {names_102}")
    
    assert "Concept101" in names_101 and "Concept102" not in names_101
    assert "Concept102" in names_102 and "Concept101" not in names_102

async def main():
    logger.info("Starting Multi-User Isolation Verification...")
    await setup_db()
    await insert_dummy_data()
    
    await verify_conversations()
    await verify_skills()
    await verify_memory()
    
    logger.info("✅ All multi-user isolation tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
