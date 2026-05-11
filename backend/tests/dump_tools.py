import asyncio
from app.infrastructure.database.sql.database import session_scope
from sqlalchemy import select
from app.models import Message

async def main():
    async with session_scope() as session:
        stmt = select(Message).where(Message.role == "tool").order_by(Message.created_at.desc()).limit(5)
        result = await session.execute(stmt)
        for msg in result.scalars():
            print(f"Tool: {msg.tool_name}, MetaData: {msg.meta_data}")

asyncio.run(main())
