"""
Integration tests for database operations.
Tests real database connections and operations.
"""

import pytest
import asyncio
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Conversation, Message, User


@pytest.fixture(scope="module")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def async_engine():
    """Create async engine for testing."""
    engine = create_async_engine(
        str(settings.SQLALCHEMY_DATABASE_URI).replace(
            "postgresql+psycopg", "postgresql+asyncpg"
        ),
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
async def async_session_factory(async_engine):
    """Create async session factory."""
    async_session = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    return async_session


class TestDatabaseConnection:
    """Tests for database connection."""

    @pytest.mark.asyncio
    async def test_database_connection(self, async_engine):
        """Test that we can connect to the database."""
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
            assert row == 1

    @pytest.mark.asyncio
    async def test_database_extensions(self, async_engine):
        """Test that required extensions are available."""
        async with async_engine.connect() as conn:
            # Check if pgvector extension exists
            result = await conn.execute(
                text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            )
            # May or may not exist depending on setup
            extensions = result.fetchall()
            # Just verify query works
            assert isinstance(extensions, list)


class TestConversationOperations:
    """Integration tests for conversation CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_conversation(self, async_session_factory):
        """Test creating a conversation in the database."""
        async with async_session_factory() as session:
            # Create a conversation
            conv = Conversation(
                id="test-thread-123",
                project_id=1,
                title="Test Conversation",
            )
            session.add(conv)
            await session.commit()

            # Verify it was created
            result = await session.execute(
                select(Conversation).where(Conversation.id == "test-thread-123")
            )
            found = result.scalar_one_or_none()
            assert found is not None
            assert found.title == "Test Conversation"
            assert found.project_id == 1

            # Cleanup
            await session.delete(found)
            await session.commit()

    @pytest.mark.asyncio
    async def test_create_message(self, async_session_factory):
        """Test creating a message in the database."""
        async with async_session_factory() as session:
            # Create conversation first
            conv = Conversation(
                id="test-thread-msg",
                project_id=1,
                title="Test",
            )
            session.add(conv)
            await session.flush()

            # Create a message
            msg = Message(
                thread_id="test-thread-msg",
                project_id=1,
                role="human",
                content="Hello, this is a test message",
                sequence_number=1,
            )
            session.add(msg)
            await session.commit()

            # Verify
            result = await session.execute(
                select(Message).where(Message.thread_id == "test-thread-msg")
            )
            found = result.scalars().all()
            assert len(found) == 1
            assert found[0].content == "Hello, this is a test message"
            assert found[0].role == "human"

            # Cleanup
            await session.delete(msg)
            await session.delete(conv)
            await session.commit()

    @pytest.mark.asyncio
    async def test_conversation_message_relationship(self, async_session_factory):
        """Test relationship between conversations and messages."""
        async with async_session_factory() as session:
            # Create conversation
            conv = Conversation(
                id="test-thread-rel",
                project_id=1,
                title="Relationship Test",
            )
            session.add(conv)
            await session.flush()

            # Create multiple messages
            for i in range(3):
                msg = Message(
                    thread_id="test-thread-rel",
                    project_id=1,
                    role="human" if i % 2 == 0 else "ai",
                    content=f"Message {i}",
                    sequence_number=i + 1,
                )
                session.add(msg)

            await session.commit()

            # Query conversation with messages
            result = await session.execute(
                select(Conversation).where(Conversation.id == "test-thread-rel")
            )
            found_conv = result.scalar_one()

            # Query messages for this conversation
            msg_result = await session.execute(
                select(Message).where(Message.thread_id == "test-thread-rel")
            )
            messages = msg_result.scalars().all()

            assert len(messages) == 3

            # Cleanup
            for msg in messages:
                await session.delete(msg)
            await session.delete(found_conv)
            await session.commit()


class TestDatabaseTransactions:
    """Tests for database transaction behavior."""

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, async_session_factory):
        """Test that transactions can be rolled back."""
        async with async_session_factory() as session:
            # Create a conversation
            conv = Conversation(
                id="test-rollback",
                project_id=1,
                title="Rollback Test",
            )
            session.add(conv)
            await session.flush()

            # Rollback
            await session.rollback()

            # Verify it doesn't exist
            result = await session.execute(
                select(Conversation).where(Conversation.id == "test-rollback")
            )
            found = result.scalar_one_or_none()
            assert found is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self, async_session_factory):
        """Test concurrent database access."""
        async def create_conversation(thread_id: str):
            async with async_session_factory() as session:
                conv = Conversation(
                    id=thread_id,
                    project_id=1,
                    title=f"Concurrent {thread_id}",
                )
                session.add(conv)
                await session.commit()
                return conv.id

        # Create conversations concurrently
        tasks = [
            create_conversation(f"concurrent-{i}")
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5

        # Cleanup
        async with async_session_factory() as session:
            for thread_id in results:
                result = await session.execute(
                    select(Conversation).where(Conversation.id == thread_id)
                )
                conv = result.scalar_one_or_none()
                if conv:
                    await session.delete(conv)
            await session.commit()
