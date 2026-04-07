#!/usr/bin/env python3
"""
数据库迁移脚本：为 learned_skills 表添加 mcp_config 字段
支持 SQLite 和 PostgreSQL
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.infrastructure.database.sql.database import engine, AsyncSessionLocal
from app.core.config import settings


async def migrate_sqlite():
    """SQLite 迁移：添加 mcp_config 列"""
    async with engine.connect() as conn:
        # 检查列是否已存在
        result = await conn.execute(text(
            "SELECT name FROM pragma_table_info('learned_skills') WHERE name='mcp_config'"
        ))
        if result.fetchone():
            print("✅ mcp_config 列已存在，跳过迁移")
            return
        
        # SQLite 添加列
        await conn.execute(text(
            "ALTER TABLE learned_skills ADD COLUMN mcp_config TEXT"
        ))
        await conn.commit()
        print("✅ SQLite: 成功添加 mcp_config 列")


async def migrate_postgres():
    """PostgreSQL 迁移：添加 mcp_config 列"""
    async with engine.connect() as conn:
        # 检查列是否已存在
        result = await conn.execute(text(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='learned_skills' AND column_name='mcp_config'
            """
        ))
        if result.fetchone():
            print("✅ mcp_config 列已存在，跳过迁移")
            return
        
        # PostgreSQL 添加 JSONB 列
        await conn.execute(text(
            "ALTER TABLE learned_skills ADD COLUMN mcp_config JSONB"
        ))
        await conn.commit()
        print("✅ PostgreSQL: 成功添加 mcp_config 列")


async def main():
    """主迁移函数"""
    db_uri = str(settings.SQLALCHEMY_DATABASE_URI)
    
    print(f"数据库 URI: {db_uri}")
    print("开始迁移...")
    
    try:
        if "sqlite" in db_uri.lower():
            await migrate_sqlite()
        else:
            await migrate_postgres()
        
        print("\n🎉 迁移完成！")
        print("\n使用说明:")
        print("  Skill 现在可以通过 mcp_config 字段自带 MCP 配置")
        print("  例如: skill.mcp_config = {'servers': [{'name': 'github', ...}], 'inherit': ['postgres']}")
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
