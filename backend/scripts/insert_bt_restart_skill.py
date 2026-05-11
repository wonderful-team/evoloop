import asyncio
import os
import sys
import json

from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.utils.time import utcnow
from sqlalchemy import select

# Add project root to path
sys.path.append(os.getcwd())


async def insert_skill():
    print("=== Re-Inserting Skill: BT Panel Restart (ID 156) ===")
    
    skill_data = {
        "id": 174,
        "name": "BT Panel Restart Website",
        "description": "Extracts Pagoda (BT) credentials from Notes app and restarts a website via the panel.",
        "trigger_patterns": json.dumps([
            "Restart BT website",
            "从备忘录找宝塔信息并重启网站"
        ]),
        "parameters": json.dumps([]),
        "steps": json.dumps([
            {
                "action": "desktop_control",
                "args": {
                    "action": "open_app",
                    "app_name": "Notes"
                }
            },
            {
                "action": "wait",
                "args": {"seconds": 2}
            },
            {
                "action": "natural_language_instruction",
                "args": {
                    "instruction": "在备忘录中搜索名为 'PTE' 或包含 '宝塔' 的笔记。从笔记内容中提取登录地址(URL)、用户名和密码。请务必完整返回这些信息。"
                }
            },
            {
                "action": "natural_language_instruction",
                "args": {
                    "instruction": "使用上一步提取的 URL 打开 Google Chrome。输入提取的用户名和密码登录宝塔面板。登录后，点击左侧菜单的‘网站’，在网站列表中找到名为‘网站’的项目，点击其右侧的‘重启’按钮。"
                }
            }
        ]),
        "tools_used": json.dumps(["desktop_control", "wait", "find_element"]),
        "status": "verified",
        "is_active": True,
        "confidence_score": 0.98
    }

    async with session_scope() as session:
        try:
            stmt = select(LearnedSkill).where(LearnedSkill.id == skill_data["id"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"Updating existing skill ID {skill_data['id']}...")
                for key, value in skill_data.items():
                    setattr(existing, key, value)
                existing.updated_at = utcnow()
            else:
                new_skill = LearnedSkill(**skill_data)
                session.add(new_skill)
                print(f"Created new skill ID {skill_data['id']}")
            
            print("=== Done ===")
            
        except Exception as e:
            print(f"Error: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(insert_skill())
