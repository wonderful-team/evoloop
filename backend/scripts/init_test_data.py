#!/usr/bin/env python3
"""Initialize test data for retry API testing."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.infrastructure.database.sql.database import engine


async def init_test_data():
    """Create test thread with messages."""
    
    messages = [
        {"id": 43, "thread_id": "test-rewind-thread-001", "role": "human", "content": "Hello, please create a calculator app"},
        {"id": 44, "thread_id": "test-rewind-thread-001", "role": "ai", "content": "I'll create a calculator app for you."},
        {"id": 45, "thread_id": "test-rewind-thread-001", "role": "human", "content": "Add more features"},
        {"id": 46, "thread_id": "test-rewind-thread-001", "role": "ai", "content": "I'll add more features to the calculator."},
    ]
    
    async with engine.begin() as conn:
        for msg in messages:
            # Check if exists
            result = await conn.execute(
                text("SELECT id FROM messages WHERE id = :id"),
                {"id": msg["id"]}
            )
            if result.scalar_one_or_none():
                print(f"Message {msg['id']} already exists")
            else:
                await conn.execute(
                    text("""
                        INSERT INTO messages (id, thread_id, role, content, project_id, is_visible, created_at)
                        VALUES (:id, :thread_id, :role, :content, 1, 1, datetime('now'))
                    """),
                    msg
                )
                print(f"Created message {msg['id']}: {msg['role']}")
    
    print("\n✅ Test data initialized!")


if __name__ == "__main__":
    asyncio.run(init_test_data())
