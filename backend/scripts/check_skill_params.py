import asyncio
import json
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from sqlalchemy import select

async def check_skills():
    async with session_scope() as db:
        stmt = select(LearnedSkill)
        result = await db.execute(stmt)
        skills = result.scalars().all()
        
        for s in skills:
            try:
                params = json.loads(s.parameters) if s.parameters else []
                print(f"ID: {s.id}, Name: {s.name}")
                print(f"  Params Type: {type(params)}")
                print(f"  Params Content: {params}")
                print("-" * 20)
            except Exception as e:
                print(f"ID: {s.id}, Name: {s.name} - ERROR parsing params: {e}")

if __name__ == "__main__":
    asyncio.run(check_skills())
