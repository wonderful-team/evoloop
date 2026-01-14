# Shared test fixtures and utilities
import asyncio
import pytest
import httpx
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, AsyncMock, patch

from tests.config import config, get_auth_headers


# ============ HTTP Client Fixtures ============

@pytest.fixture
def sync_client() -> Generator[httpx.Client, None, None]:
    """Synchronous HTTP client for API tests."""
    with httpx.Client(
        base_url=config.API_BASE_URL,
        headers=get_auth_headers(),
        timeout=config.API_TIMEOUT
    ) as client:
        yield client


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Asynchronous HTTP client for API tests."""
    async with httpx.AsyncClient(
        base_url=config.API_BASE_URL,
        headers=get_auth_headers(),
        timeout=config.API_TIMEOUT
    ) as client:
        yield client


# ============ SSE Client Fixture ============

@pytest.fixture
async def sse_client():
    """SSE client for streaming tests."""
    import httpx_sse
    
    async with httpx.AsyncClient(
        base_url=config.API_BASE_URL,
        headers=get_auth_headers(),
        timeout=httpx.Timeout(config.SSE_TIMEOUT)
    ) as client:
        yield client


# ============ Database Fixtures ============

@pytest.fixture
async def db_session():
    """Provides a database session for tests."""
    from app.infrastructure.database.sql.database import session_scope
    async with session_scope() as session:
        yield session


@pytest.fixture
async def clean_test_data(db_session):
    """Cleanup test data after tests."""
    yield
    # Cleanup logic here if needed


# ============ Mock Fixtures ============

@pytest.fixture
def mock_llm():
    """Mock LLM for unit tests."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(
        content="Mock LLM response",
        tool_calls=[]
    ))
    return mock


@pytest.fixture
def mock_redis():
    """Mock Redis for unit tests."""
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


# ============ Project Context Fixtures ============

@pytest.fixture
def project_context() -> dict:
    """Returns the test project context."""
    return {
        "project_id": config.PROJECT_ID,
        "project_path": config.PROJECT_PATH,
        "project_name": config.PROJECT_NAME
    }


@pytest.fixture
def thread_id() -> str:
    """Generates a unique thread ID for each test."""
    return config.generate_thread_id()


# ============ Agent State Fixtures ============

@pytest.fixture
def base_agent_state(thread_id, project_context) -> dict:
    """Base agent state for node tests."""
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content="Test message")],
        "project_id": project_context["project_id"],
        "current_plan": None,
        "next_node": None,
        "hitl_state": None,
        "scratchpad": {},
        "retry_count": 0
    }


@pytest.fixture
def runnable_config(thread_id, project_context) -> dict:
    """RunnableConfig for node tests."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "project_id": project_context["project_id"],
            "working_directory": project_context["project_path"]
        }
    }


# ============ Helper Functions ============

async def wait_for_sse_event(client, thread_id: str, event_type: str, timeout: int = 30):
    """Wait for a specific SSE event."""
    import httpx_sse
    
    url = f"/api/v1/stream/chat/{thread_id}"
    async with httpx_sse.aconnect_sse(client, "GET", url) as event_source:
        async for event in event_source.aiter_sse():
            if event.event == event_type:
                return event.data
    return None


async def send_chat_message(client: httpx.AsyncClient, message: str, thread_id: str) -> dict:
    """Send a chat message and return response."""
    response = await client.post("/api/v1/chat", json={
        "message": message,
        "thread_id": thread_id,
        "project_id": config.PROJECT_ID
    })
    return response.json()


def assert_sse_event_structure(event_data: dict, required_fields: list):
    """Assert SSE event has required structure."""
    for field in required_fields:
        assert field in event_data, f"Missing field: {field}"
