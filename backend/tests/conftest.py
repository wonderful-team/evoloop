"""
Pytest Configuration and Shared Fixtures

This module provides:
1. Test markers and configuration
2. Shared fixtures for database, cache, LLM mocking
3. Test utilities and helpers
4. Async test support
"""

import asyncio
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

# =============================================================================
# Critical: Set test environment BEFORE any app imports
# =============================================================================

# Load test .env file first
from pathlib import Path
test_env_path = Path(__file__).parent / ".env"
if test_env_path.exists():
    with open(test_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

# Load test .env file first (before setting defaults)
test_env_path = Path(__file__).parent / ".env"
if test_env_path.exists():
    with open(test_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

# Ensure critical test settings (only if not already set from .env)
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("POSTGRES_DB", "app")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "admin888")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("USE_NEO4J_MEMORY", "false")
os.environ.setdefault("EXECUTION_MODE", "local")
os.environ.setdefault("SECRET_KEY", "test_secret_key")

# Mock thread_store before importing app modules
_mock_thread_store = MagicMock()
_mock_thread_store.get = Mock(return_value=None)
_mock_thread_store.set = Mock()
_mock_thread_store.clear = Mock()
sys.modules["app.core.context.thread_store"] = MagicMock(
    thread_context_store=_mock_thread_store
)

import pytest
import pytest_asyncio

# =============================================================================
# Test Markers
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line("markers", "integration: Integration tests (requires external services)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (full system)")
    config.addinivalue_line("markers", "slow: Slow tests (>1s)")
    config.addinivalue_line("markers", "llm: Tests requiring LLM mocking")
    config.addinivalue_line("markers", "db: Tests requiring database")
    config.addinivalue_line("markers", "neo4j: Tests requiring Neo4j")
    config.addinivalue_line("markers", "redis: Tests requiring Redis")


# =============================================================================
# Event Loop
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Test Data Paths
# =============================================================================

@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return the path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def test_settings():
    """Provide test-specific settings."""
    from app.core.config import Settings

    settings = Settings(
        ENVIRONMENT="local",
        POSTGRES_DB="evoloop_test",
        REDIS_URL="redis://localhost:6379/15",
        USE_NEO4J_MEMORY=False,
        EXECUTION_MODE="local",
        LOG_LEVEL="DEBUG",
    )
    return settings


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[Any, None]:
    """
    Provide a database session for tests.

    This fixture:
    1. Creates a new session for each test
    2. Rolls back all changes after the test
    3. Cleans up connections
    """
    from app.infrastructure.database.sql.database import async_session_maker, engine
    from sqlalchemy import text

    async with async_session_maker() as session:
        # Start nested transaction
        await session.begin_nested()

        yield session

        # Rollback all changes
        await session.rollback()

    # Clean up
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Provide a database engine for tests."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/evoloop_test",
        echo=False,
        future=True,
    )

    yield engine

    await engine.dispose()


@pytest.fixture(scope="function")
def mock_db_session():
    """Provide a mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = Mock()
    session.add_all = Mock()
    session.delete = Mock()
    return session


# =============================================================================
# Memory System Fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def memory_manager():
    """Provide a memory manager instance for tests."""
    from app.core.memory.manager import MemoryManager

    manager = MemoryManager()

    # Mock the backends to avoid external dependencies
    manager.short_term = AsyncMock()
    manager.long_term = AsyncMock()
    manager.preferences = AsyncMock()
    manager.graph = AsyncMock()

    return manager


@pytest_asyncio.fixture(scope="function")
async def short_term_memory():
    """Provide a short-term memory instance."""
    from app.core.memory.backends.sql_short_term import SqlShortTermMemory

    memory = SqlShortTermMemory()
    memory._initialized = True

    # Mock the session operations
    memory.add_message = AsyncMock()
    memory.get_context = AsyncMock(return_value=[])
    memory.clear = AsyncMock()

    return memory


@pytest.fixture(scope="function")
def mock_neo4j_memory():
    """Provide a mock Neo4j long-term memory."""
    memory = AsyncMock()
    memory.add_concept = AsyncMock()
    memory.search_concepts = AsyncMock(return_value=[])
    memory.add_episode = AsyncMock()
    memory.get_episodes = AsyncMock(return_value=[])
    memory.initialize = AsyncMock()
    return memory


# =============================================================================
# Context Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def evo_context():
    """Provide a fresh EvoContext for tests."""
    from app.core.context.manager import EvoContext

    return EvoContext(
        request_id="test-request-001",
        user_id="test-user-001",
        project_id=1,
        thread_id="test-thread-001",
        working_directory="/tmp/test",
        language="en",
    )


@pytest.fixture(scope="function")
def context_manager(evo_context):
    """Provide a context manager with test context set."""
    from app.core.context.manager import ContextManager

    token = ContextManager.set(evo_context)
    yield ContextManager
    ContextManager.reset(token)


@pytest_asyncio.fixture(scope="function")
async def context_bus():
    """Provide a consciousness bus for tests."""
    from app.core.context.consciousness import ConsciousnessBus

    bus = ConsciousnessBus(thread_id="test-thread-001")
    return bus


# =============================================================================
# LLM Mocking Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def mock_llm_response():
    """Factory for creating mock LLM responses."""

    def _create_response(
        content: str = "Test response",
        tool_calls: Optional[List[Dict]] = None,
    ):
        response = MagicMock()
        response.content = content
        response.tool_calls = tool_calls or []
        return response

    return _create_response


@pytest.fixture(scope="function")
def mock_llm_factory(mock_llm_response):
    """Mock the LLMFactory to return predictable responses."""

    def _mock_factory(responses: List[Dict] = None):
        responses = responses or [{"content": "Test response"}]
        call_count = 0

        def _create_llm(*args, **kwargs):
            nonlocal call_count
            llm = MagicMock()

            async def _ainvoke(*args, **kwargs):
                nonlocal call_count
                if call_count < len(responses):
                    resp = responses[call_count]
                    call_count += 1
                    return mock_llm_response(**resp)
                return mock_llm_response(content="Default response")

            llm.ainvoke = _ainvoke
            llm.bind_tools = Mock(return_value=llm)
            return llm

        return _create_llm

    return _mock_factory


@pytest.fixture(scope="function")
def mock_openai_client():
    """Provide a mock OpenAI client."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client


# =============================================================================
# Event Bus Fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def event_bus():
    """Provide a fresh event bus for tests."""
    from app.core.events.base import AsyncEventBus

    bus = AsyncEventBus(name="test-bus")
    yield bus
    bus.clear()


@pytest.fixture(scope="function")
def mock_event_handler():
    """Provide a mock event handler."""
    return AsyncMock()


# =============================================================================
# Tool Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def tool_registry():
    """Provide a tool registry for tests."""
    from app.core.tools.registry import AutoDiscoveryRegistry

    registry = AutoDiscoveryRegistry()
    return registry


@pytest.fixture(scope="function")
def mock_tool():
    """Factory for creating mock tools."""

    def _create_tool(
        name: str = "test_tool",
        description: str = "A test tool",
        return_value: Any = "Tool result",
    ):
        tool = MagicMock()
        tool.name = name
        tool.description = description
        tool.invoke = AsyncMock(return_value=return_value)
        tool.arun = AsyncMock(return_value=return_value)
        return tool

    return _create_tool


@pytest_asyncio.fixture(scope="function")
async def tool_executor():
    """Provide a tool executor for tests."""
    from app.core.tools.executor import ToolExecutor

    return ToolExecutor()


# =============================================================================
# Agent State Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def agent_state():
    """Provide a basic agent state for tests."""
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content="Test message")],
        "project_id": 1,
        "iteration_count": 0,
        "scratchpad": {},
        "execution_ticket": None,
    }


@pytest.fixture(scope="function")
def execution_ticket():
    """Provide a sample execution ticket."""
    return {
        "ticket_type": "test_task",
        "priority": "normal",
        "acceptance_criteria": ["Complete the test"],
        "focus_paths": ["/tmp/test.py"],
        "topic": "Testing",
        "parameters": {},
        "constraints": [],
        "expected_outcomes": ["Test passes"],
    }


# =============================================================================
# Engine Fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def agent_engine():
    """Provide an AgentEngine instance with mocked LLM."""
    from app.core.engine import AgentEngine

    # Return the class for static method access
    return AgentEngine


@pytest.fixture(scope="function")
def runnable_config():
    """Provide a runnable config for tests."""
    return {
        "configurable": {
            "thread_id": "test-thread-001",
            "run_id": "test-run-001",
        },
        "metadata": {
            "project_id": 1,
        },
    }


# =============================================================================
# Multimodal Synthesis Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def mock_vision_llm():
    """Provide a mock Vision LLM for multimodal synthesis tests."""
    from tests.mocks.vision_llm import MockVisionLLM
    return MockVisionLLM()


@pytest.fixture(scope="function")
def mock_compressed_frames():
    """Provide mock compressed frames for testing."""
    from app.core.learning.frame_compressor import CompressedFrame

    frames = []
    for i in range(3):
        frame = CompressedFrame(
            data=b"fake_jpeg_data_" + str(i).encode(),
            width=768,
            height=432,
            original_size=(1920, 1080),
            compression_ratio=0.15,
            detail_level="low"
        )
        frame.timestamp = 1000.0 + i * 2
        frame.description = f"Test frame {i}"
        frame.norm_events = [{
            'action': 'mouse_click',
            'position': (0.5, 0.5),
            'target_text': f'Button{i}'
        }]
        frames.append(frame)
    return frames


@pytest.fixture(scope="function")
def sample_recording_session():
    """Provide a sample recording session."""
    from app.core.learning.multimodal_synthesizer import RecordingSession

    return RecordingSession(
        video_path="/tmp/test_video.mp4",
        session_id="test-session-123",
        task_description="Send message to Zhang San in WeChat",
        thread_id="thread-456"
    )


@pytest.fixture(scope="function")
def sample_trace_events():
    """Provide sample trace events."""
    events = []
    base_time = 1000.0

    for i in range(3):
        event = MagicMock()
        event.timestamp = base_time + i * 2
        event.action_type = "mouse_click"
        event.mouse_x = 960
        event.mouse_y = 540
        event.target_text = f"Button{i}"
        event.window_title = "WeChat"
        event.app_name = "WeChat"
        event.key_name = None
        events.append(event)

    return events


@pytest.fixture(scope="function")
def frame_compressor():
    """Provide a FrameCompressor instance."""
    from app.core.learning.frame_compressor import FrameCompressor
    return FrameCompressor()


@pytest.fixture(scope="function")
def keyframe_selector():
    """Provide a KeyframeSelector instance."""
    from app.core.learning.frame_compressor import KeyframeSelector
    return KeyframeSelector()


@pytest.fixture(scope="function")
def coordinate_normalizer():
    """Provide a CoordinateNormalizer instance."""
    from app.core.learning.frame_compressor import CoordinateNormalizer
    return CoordinateNormalizer(1920, 1080)


# =============================================================================
# Learning System Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def skill_discovery():
    """Provide a skill discovery instance with mocked backend."""
    from app.core.learning.discovery import SkillDiscovery

    discovery = SkillDiscovery()
    discovery._cache = {}

    # Mock the search methods
    discovery.exact_search = AsyncMock(return_value=(None, []))
    discovery.match = AsyncMock(return_value=None)
    discovery.retrieve = AsyncMock(return_value=[])

    return discovery


@pytest.fixture(scope="function")
def mock_learned_skill():
    """Factory for creating mock learned skills."""

    def _create_skill(
        name: str = "test_skill",
        namespace: str = "test/namespace",
        instructions: str = "Test instructions",
    ):
        from app.models.learning import LearnedSkill

        skill = MagicMock(spec=LearnedSkill)
        skill.name = name
        skill.namespace = namespace
        skill.instructions = instructions
        skill.trigger_patterns = ["test pattern"]
        skill.confidence_threshold = 0.7
        return skill

    return _create_skill


# =============================================================================
# Prompt Builder Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def supervisor_prompt_builder():
    """Provide a SupervisorPromptBuilder for tests."""
    from app.core.engine.prompts.supervisor_builder import SupervisorPromptBuilder

    return SupervisorPromptBuilder(
        project_id=1,
        active_plan_context="No active plan",
        iteration_count=0,
        sys_info="Test system",
        context={},
    )


@pytest.fixture(scope="function")
def developer_prompt_builder():
    """Provide a DeveloperPromptBuilder for tests."""
    from app.core.engine.prompts.developer_builder import DeveloperPromptBuilder

    return DeveloperPromptBuilder(
        state={},
        context={},
        project_id=1,
        skills=[],
    )


# =============================================================================
# HTTP/Client Fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def async_client():
    """Provide an async HTTP client for tests."""
    from httpx import AsyncClient

    async with AsyncClient() as client:
        yield client


@pytest.fixture(scope="function")
def mock_fastapi_app():
    """Provide a mock FastAPI app."""
    from fastapi import FastAPI

    app = FastAPI()
    return app


# =============================================================================
# Utility Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def freeze_time():
    """Freeze time for deterministic tests."""
    from unittest.mock import patch

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
        yield mock_datetime


@pytest.fixture(scope="function")
def capture_logs(caplog):
    """Capture log output for testing."""
    caplog.set_level("DEBUG")
    return caplog


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest_asyncio.fixture(autouse=True, scope="function")
async def cleanup_after_test():
    """Automatically cleanup resources after each test."""
    yield

    # Cleanup logic runs after test
    # Add any global cleanup here


# =============================================================================
# Parametrized Test Data
# =============================================================================

@pytest.fixture(
    params=[
        pytest.param("simple", marks=[pytest.mark.unit]),
        pytest.param("complex", marks=[pytest.mark.integration]),
    ]
)
def task_complexity(request):
    """Provide different task complexities for parametrized tests."""
    return request.param
