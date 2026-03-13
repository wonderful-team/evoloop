import asyncio
import logging
import json
from sqlmodel import select
from app.infrastructure.database.sql.database import session_scope
from app.models.system import McpServer
from app.initial_data import init_mcp

logging.basicConfig(level=logging.INFO)

async def test_mcp_sync():
    # 1. Manually set an OLD/Mismatched path in DB
    async with session_scope() as session:
        result = await session.execute(select(McpServer).where(McpServer.name == "filesystem"))
        fs = result.scalars().first()
        if fs:
            print(f"Current path in DB: {fs.args}")
            # Change it to something else
            fs.args = json.dumps(["-y", "@modelcontextprotocol/server-filesystem", "/tmp/wrong_path"])
            session.add(fs)
            print("Set path to /tmp/wrong_path in DB")
    
    # 2. Run init_mcp (which should detect the mismatch against current settings.WORKSPACE_ROOT)
    print("\nRunning init_mcp synchronization...")
    await init_mcp()
    
    # 3. Verify it was updated back to match WORKSPACE_ROOT (from .env or config)
    async with session_scope() as session:
        result = await session.execute(select(McpServer).where(McpServer.name == "filesystem"))
        fs = result.scalars().first()
        print(f"\nUpdated path in DB: {fs.args}")

if __name__ == "__main__":
    asyncio.run(test_mcp_sync())
