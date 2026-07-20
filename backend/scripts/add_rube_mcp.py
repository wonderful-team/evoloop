import asyncio
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.database.resource_manager import db_resource_manager
from app.infrastructure.database.sql.database import session_scope
from app.models.system import McpServer
from sqlalchemy import select

async def add_mcp_server():
    # Initialize the database resource manager first!
    await db_resource_manager.initialize()
    
    async with session_scope() as db:
        # Check if it already exists
        stmt = select(McpServer).where(McpServer.name == "rube")
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            print("MCP server 'rube' already exists in the database. Updating it...")
            existing.command = "https://rube.app/mcp"
            existing.args = "[]"
            existing.env = "{}"
            existing.enabled = True
            print("Successfully updated MCP server 'rube'.")
        else:
            print("Adding MCP server 'rube' to the database...")
            new_server = McpServer(
                name="rube",
                command="https://rube.app/mcp",
                args="[]",
                env="{}",
                enabled=True
            )
            db.add(new_server)
            print("Successfully added MCP server 'rube'.")

if __name__ == "__main__":
    asyncio.run(add_mcp_server())
