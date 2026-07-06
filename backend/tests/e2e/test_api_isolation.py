import asyncio
import logging
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.deps import get_current_user_optional
from app.models import User
from app.infrastructure.database.resource_manager import db_resource_manager
from sqlmodel import select, delete
from app.models.conversation import Conversation
from app.infrastructure.database import session_scope

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("e2e_api_isolation")

def set_user(user_id: int):
    async def _override():
        return User(id=user_id, is_active=True)
    app.dependency_overrides[get_current_user_optional] = _override

async def setup_test_data():
    async with session_scope() as db:
        await db.execute(delete(Conversation))
        db.add(Conversation(id="thread_e2e_101", title="User 101 Conv", member_id=101, project_id=1))
        db.add(Conversation(id="thread_e2e_102", title="User 102 Conv", member_id=102, project_id=1))
        await db.commit()

async def main():
    logger.info("Initializing DB for E2E testing...")
    await db_resource_manager.initialize()
    await setup_test_data()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test 1: User 101 Lists Conversations
        set_user(101)
        resp = await client.get("/api/v1/conversations/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = [c["thread_id"] for c in data]
        assert "thread_e2e_101" in ids
        assert "thread_e2e_102" not in ids
        logger.info("✅ GET /conversations/ -> User 101 isolated correctly.")

        # Test 2: User 102 Updates User 101's Conversation (Should Fail)
        set_user(102)
        resp = await client.patch("/api/v1/conversations/thread_e2e_101", json={"title": "Hacked"})
        assert resp.status_code == 403
        logger.info("✅ PATCH /conversations/{id} -> User 102 cannot modify User 101's conv (403).")

        # Test 3: User 102 Deletes User 101's Conversation (Should Fail)
        resp = await client.delete("/api/v1/conversations/thread_e2e_101")
        assert resp.status_code == 403
        logger.info("✅ DELETE /conversations/{id} -> User 102 cannot delete User 101's conv (403).")

        # Test 4: User 101 Deletes Own Conversation
        set_user(101)
        resp = await client.delete("/api/v1/conversations/thread_e2e_101")
        assert resp.status_code == 200
        logger.info("✅ DELETE /conversations/{id} -> User 101 can delete own conv (200).")

    logger.info("✅ All E2E API isolation tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
