import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.database import session_scope
from app.models import Message, MessageReference
from sqlalchemy import select
from sqlalchemy.orm import selectinload

async def check():
    async with session_scope() as session:
        # 查找 changeset 测试的 Thread
        stmt = select(Message).where(Message.thread_id.like('real-changeset-test%')).options(selectinload(Message.references))
        res = await session.execute(stmt)
        msgs = res.scalars().all()
        
        print(f"\n--- Scenario 3 Message Audit ---")
        for m in msgs:
            print(f"Msg {m.sequence_number} ({m.role}, {m.category}): {len(m.references)} refs")
            for r in m.references:
                print(f"  - [{r.type}] {r.target_name} (meta: {r.meta_data})")

if __name__ == "__main__":
    asyncio.run(check())
