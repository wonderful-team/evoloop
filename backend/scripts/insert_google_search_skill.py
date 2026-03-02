import asyncio
import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.models.learning import LearnedSkill
from app.utils.time import utcnow

async def insert_skill():
    print("=== Inserting Sample Skill: Google Search ===")
    
    skill_data = {
        "name": "Google Search",
        "description": "Opens Google and searches for a query provided by the user.",
        "trigger_patterns": json.dumps([
            "Search for {{query}}",
            "Google search {{query}}",
            "Look up {{query}} on Google"
        ]),
        "parameters": json.dumps([
            {
                "name": "query",
                "type": "string",
                "description": "What do you want to search for?",
                "required": True
            }
        ]),
        "steps": json.dumps([
            {
                "action": "open_url",
                "args": {"url": "https://www.google.com"}
            },
            {
                "action": "wait",
                "args": {"seconds": 2}
            },
            {
                "action": "type_text",
                "args": {
                    "text": "{{query}}",
                    "selector": "textarea[name='q']"
                }
            },
            {
                "action": "press_key",
                "args": {"key": "Enter"}
            }
        ]),
        "tools_used": json.dumps(["browser"]),
        "status": "verified",
        "is_active": True,
        "success_count": 12,
        "confidence_score": 0.95
    }

    async with AsyncSessionLocal() as session:
        try:
            # Check if exists
            from sqlalchemy import select
            stmt = select(LearnedSkill).where(LearnedSkill.name == skill_data["name"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"⚠️ Skill '{skill_data['name']}' already exists. Updating...")
                for key, value in skill_data.items():
                    setattr(existing, key, value)
                existing.updated_at = utcnow()
            else:
                new_skill = LearnedSkill(**skill_data)
                session.add(new_skill)
                print(f"✅ Created new skill: {skill_data['name']}")
            
            await session.commit()
            print("=== Done ===")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            await session.rollback()
            raise

if __name__ == "__main__":
    asyncio.run(insert_skill())
