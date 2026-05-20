import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.database.sql.database import session_scope
from app.models import Message, MessageReference
from sqlalchemy import select

from app.infrastructure.database.resource_manager import db_resource_manager

async def check():
    await db_resource_manager.initialize()
    async with session_scope() as session:
        stmt = select(MessageReference).where(MessageReference.type == 'changeset')
        res = await session.execute(stmt)
        refs = res.scalars().all()
        
        print(f"\n--- Global Changeset Audit ---")
        print(f"Total changeset refs in DB: {len(refs)}")
        for r in refs:
            # 获取对应的 Message 信息
            msg_stmt = select(Message).where(Message.id == r.message_id)
            msg_res = await session.execute(msg_stmt)
            msg = msg_res.scalar()
            
            print(f"  - MessageID: {r.message_id}")
            if msg:
                print(f"    ThreadID: {msg.thread_id}, Seq: {msg.sequence_number}, Role: {msg.role}")
            print(f"    Target: {r.target_name}, Meta: {r.meta_data}")

if __name__ == "__main__":
    asyncio.run(check())
