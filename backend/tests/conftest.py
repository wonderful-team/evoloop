# Shared test fixtures and utilities
import asyncio
import pytest
import httpx
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, AsyncMock, patch

from tests.config import config, get_auth_headers
from app.main import app


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
    """Asynchronous HTTP client for API tests (In-Process)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=get_auth_headers(),
        timeout=config.API_TIMEOUT
    ) as client:
        yield client
        await client.aclose()


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
        await client.aclose()


# ============ Database Fixtures ============

@pytest.fixture
async def db_session():
    """Provides a database session for tests. Skips if DB unavailable."""
    try:
        from app.infrastructure.database.sql.database import session_scope
        async with session_scope() as session:
            yield session
    except Exception as e:
        pytest.skip(f"Database unavailable: {e}")


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
    mock = MagicMock()
    mock.pubsub.return_value.subscribe = AsyncMock()
    # Ensure standard methods like get/set return coroutines if awaited
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    return mock


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
def sandbox_temp_dir(tmp_path):
    """
    Creates a temporary directory INSIDE the backend project for file tests.
    This bypasses the security sandbox that blocks /tmp access.
    """
    import os
    import shutil
    
    # Use the backend project directory (where tests are run from)
    # Not config.PROJECT_PATH which might point to a different project
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sandbox_dir = os.path.join(backend_dir, ".test_sandbox")
    os.makedirs(sandbox_dir, exist_ok=True)
    
    # Create unique test subdir
    test_dir = os.path.join(sandbox_dir, tmp_path.name)
    os.makedirs(test_dir, exist_ok=True)
    
    yield test_dir
    
    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.fixture
def mock_security_bypass():
    """
    Fixture to bypass file security checks for testing.
    Use with caution - only for unit tests.
    """
    with patch('app.domain.tools.files.path_utils.validate_path') as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def temp_project_with_files(sandbox_temp_dir):
    """
    Creates a temporary project with sample files for testing.
    Located inside the project sandbox to pass security checks.
    """
    import os
    
    # Create sample files
    with open(os.path.join(sandbox_temp_dir, "README.md"), "w") as f:
        f.write("# Test Project\n\nThis is a test.\n")
    
    with open(os.path.join(sandbox_temp_dir, "main.py"), "w") as f:
        f.write("def main():\n    print('Hello')\n\nif __name__ == '__main__':\n    main()\n")
    
    os.makedirs(os.path.join(sandbox_temp_dir, "src"), exist_ok=True)
    with open(os.path.join(sandbox_temp_dir, "src", "utils.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    
    return sandbox_temp_dir


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
