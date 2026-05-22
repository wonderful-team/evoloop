"""
Thread-safe SQLite connection pool with WAL mode for knowledge base services.

Provides pooled connections to avoid thread-safety issues with SQLite
in concurrent environments (e.g., FastAPI with multiple workers/threads).
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KnowledgeConnectionPool:
    """
    Thread-safe SQLite connection pool with WAL mode support.

    Usage:
        pool = KnowledgeConnectionPool(Path("~/.evoloop/knowledge/search.db"))

        with pool.acquire() as conn:
            rows = conn.execute("SELECT * FROM fts_documents").fetchall()

    Features:
    - Connection pooling (max 5 by default)
    - WAL mode for concurrent reads during writes
    - Automatic connection recycling
    - Thread-safe acquire/release
    """

    def __init__(self, db_path: Path, max_connections: int = 5):
        """
        Initialize the connection pool.

        Args:
            db_path: Path to the SQLite database file
            max_connections: Maximum number of connections to keep in pool
        """
        self.db_path = Path(db_path)
        self.max_connections = max_connections
        self._pool: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._initialized = False

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with WAL mode enabled."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        return conn

    @contextmanager
    def acquire(self):
        """
        Acquire a connection from the pool.

        Yields:
            sqlite3.Connection: A database connection

        Example:
            with pool.acquire() as conn:
                conn.execute("INSERT INTO ...")
                conn.commit()
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            with self._lock:
                if self._pool:
                    conn = self._pool.pop()
                else:
                    conn = self._create_connection()
            yield conn
        finally:
            if conn is not None:
                with self._lock:
                    if len(self._pool) < self.max_connections:
                        self._pool.append(conn)
                    else:
                        try:
                            conn.close()
                        except Exception:
                            pass

    def close_all(self) -> None:
        """Close all pooled connections."""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()

    def __del__(self):
        """Cleanup on garbage collection."""
        try:
            self.close_all()
        except Exception:
            pass
