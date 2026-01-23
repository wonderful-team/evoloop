
import asyncio
import sys
import os

# Ensure backend modules are found
sys.path.append(os.getcwd())

from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models import Message
from sqlalchemy import select, func

async def analyze_thread(target_thread_id):
    async with session_scope() as session:
        # 2. Check timestamps of suspicious messages
        print("\nChecking timestamps of 'requirement_analyst' messages:")
        suspicious_ids = [1486, 1508, 1629, 1631, 1633]
        stmt = select(Message).where(Message.id.in_(suspicious_ids))
        result = await session.execute(stmt)
        msgs = result.scalars().all()
        for m in msgs:
            print(f"ID: {m.id} | Created: {m.created_at} | Thread: {m.thread_id} | Content: {m.content}")

        # 4. ABSOLUTE LAST 5 MESSAGES IN DB
        print("\nABSOLUTE LAST 5 MESSAGES IN DB (System Wide):")
        stmt = select(Message).order_by(Message.id.desc()).limit(5)
        result = await session.execute(stmt)
        msgs = result.scalars().all()
        for m in msgs:
            print(f"ID: {m.id} | Created: {m.created_at} | Thread: {m.thread_id} | Role: {m.role} | Content: {(m.content or '')[:50]}...")




if __name__ == "__main__":
    thread_id = "task-8-1768594470"
    asyncio.run(analyze_thread(thread_id))
