import aiosqlite
import logging
import os
from pathlib import Path
from typing import Any, List, Optional
from datetime import datetime

from app.core.memory.models import MemoryEntry, MemoryType, MemoryTier, PrivacyLevel

logger = logging.getLogger(__name__)

class SqliteMemoryIndex:
    """
    SQLite-based index for memory metadata.
    Provides fast filtering and lookup for the FileMemoryStorage backend.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self):
        """Create tables if they don't exist."""
        if self._initialized:
            return
            
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            # Main metadata table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memory_index (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    privacy TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    path TEXT NOT NULL,
                    project_id INTEGER,
                    user_id TEXT,
                    source TEXT,
                    source_message_id TEXT,
                    run_id TEXT,
                    content_hash TEXT,
                    confidence REAL,
                    utility_score REAL,
                    version INTEGER,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            
            # Indexes for common search patterns
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_project ON memory_index(project_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_user ON memory_index(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_run ON memory_index(run_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_msg ON memory_index(source_message_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_hash ON memory_index(content_hash)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_index(type)")
            
            await db.commit()
            
        self._initialized = True
        logger.info(f"[SqliteIndex] Initialized at {self.db_path}")

    async def upsert(self, entry: MemoryEntry, file_path: str):
        """Insert or update a memory entry in the index."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO memory_index (
                    id, type, tier, privacy, title, description, path,
                    project_id, user_id, source, source_message_id, run_id,
                    content_hash, confidence, utility_score, version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id, entry.type.value, entry.tier.value, entry.privacy.value,
                entry.title, entry.description, str(file_path),
                entry.project_id, entry.user_id, entry.source,
                entry.source_message_id, entry.run_id,
                entry.content_hash, entry.confidence, entry.utility_score,
                entry.version, entry.created_at.isoformat(),
                entry.updated_at.isoformat()
            ))
            await db.commit()

    async def delete(self, entry_id: str) -> None:
        """Delete an entry from the index."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM memory_index WHERE id = ?", (entry_id,))
            await db.commit()

    async def close(self) -> None:
        """Close connection (no-op for connection-per-call pattern)."""
        self._initialized = False
        logger.debug(f"[SqliteIndex] Closed (cleared initialized flag) for {self.db_path}")

    async def delete_by_run_id(self, run_id: str) -> int:
        """Delete all entries associated with a run_id."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM memory_index WHERE run_id = ?", (run_id,))
            count = cursor.rowcount
            await db.commit()
            return count

    async def delete_by_source_message_id(self, msg_id: str) -> int:
        """Delete all entries associated with a source_message_id."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM memory_index WHERE source_message_id = ?", (msg_id,))
            count = cursor.rowcount
            await db.commit()
            return count

    async def get_by_id(self, memory_id: str) -> Optional[dict]:
        """Get an entry's metadata by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM memory_index WHERE id = ?", (memory_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def search(self, filters: dict, limit: int = 100) -> List[dict]:
        """
        Search for entries matching specific metadata filters.
        """
        query = "SELECT * FROM memory_index WHERE 1=1"
        params = []
        
        for key, value in filters.items():
            if value is not None:
                query += f" AND {key} = ?"
                params.append(value)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def list_all(self) -> List[dict]:
        """List all indexed metadata."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM memory_index") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def clear(self):
        """Wipe the entire index."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM memory_index")
            await db.commit()

    async def get_count(self) -> int:
        """Get total number of indexed entries."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM memory_index") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
