
import asyncio
import os
import sys
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.infrastructure.database.sql.database import get_db_session

async def list_tables():
    print("Listing DB Tables...")
    try:
        async with get_db_session() as session:
            result = await session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
            tables = result.scalars().all()
            print("Found Tables:")
            for t in tables:
                print(f" - {t}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(list_tables())
