"""
Synchronous database engine for EvoLoop Client.

PostgreSQL support has been moved to the server branch.
"""
from sqlmodel import Session, create_engine

from app.core.config import settings

# SQLite sync engine (client-only)
engine = create_engine(
    f"sqlite:///{settings.SQLITE_PATH}",
    echo=settings.DB_ECHO,
    connect_args={"check_same_thread": False},
)


def init_db(session: Session) -> None:
    """Initialize database (tables are created via SQLModel)."""
    pass
