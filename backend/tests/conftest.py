"""
Pytest configuration for EvoLoop Backend tests.

This module mocks heavy dependencies that are not available in the test environment
and patches application-level singletons to prevent slow initialization and
background task leaks during test execution.

MOCK ARCHITECTURE:
- "Always-on" mocks (module level): Vision frameworks, event-loop leak prevention,
  HookSystem side-effect suppression, and optional heavy dependencies.
- "Unit-test-only" mocks (conditional): Task Queue, Vector Store, Resource Manager,
  SystemConfigService. These are skipped when `--integration` is passed so that
  integration tests can exercise real backend implementations.
"""
import sys
from unittest.mock import MagicMock, AsyncMock
from contextlib import asynccontextmanager


# =============================================================================
# 0. Pre-inject Vision modules to prevent heavy module-level initialization
# =============================================================================
# PipelineManager() and VisionEngine() are instantiated at module import time
# and pull in heavy native frameworks (pyobjc, Vision, Quartz). Pre-injecting
# mock modules prevents this entirely.
_mock_vision_pipeline = MagicMock()
_mock_vision_pipeline.pipeline_manager = MagicMock()
_mock_vision_pipeline.pipeline_manager.providers = []
_mock_vision_pipeline.merge_elements = lambda results: []
sys.modules["app.core.vision.pipeline.manager"] = _mock_vision_pipeline

_mock_vision_engine = MagicMock()
_mock_vision_engine.vision_engine = MagicMock()
sys.modules["app.core.vision.engine"] = _mock_vision_engine


# =============================================================================
# 1-4. Unit-test-only mocks (applied in pytest_configure when --integration absent)
# =============================================================================
# These mocks are deferred to pytest_configure so that integration tests can
# opt out via the --integration flag and exercise real backend implementations.

class _NoOpTaskScheduler:
    """No-op scheduler for tests. Prevents Huey SQLite initialization."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def task(self, func=None, *, name=None, bind=False, retries=0, retry_delay=0, **options):
        def decorator(f):
            import asyncio

            def wrapper(*args, **kwargs):
                if asyncio.iscoroutinefunction(f):
                    return asyncio.run(f(*args, **kwargs))
                return f(*args, **kwargs)

            wrapper.__name__ = f.__name__
            wrapper.__module__ = f.__module__
            wrapper.__doc__ = f.__doc__
            wrapper.delay = lambda *a, **kw: MagicMock(
                id="mock-task", ready=lambda: True, successful=lambda: True
            )
            wrapper.apply_async = lambda args=None, kwargs=None, **opts: wrapper.delay(
                *(args or ()), **(kwargs or {})
            )
            wrapper.name = name or f"{f.__module__}.{f.__name__}"
            # Expose .func so tests that introspect task wrappers continue to work
            wrapper.func = wrapper
            return wrapper

        if func is not None:
            return decorator(func)
        return decorator

    def send_task(self, name, args=None, kwargs=None, **options):
        return MagicMock(id="mock-task", ready=lambda: True, successful=lambda: True)

    def start(self, **kwargs):
        pass

    def worker_main(self, **kwargs):
        pass

    def periodic_task(self, cron, name=None, **kwargs):
        def decorator(f):
            return f

        return decorator


@asynccontextmanager
async def _mock_raw_connection():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()
    conn.cursor = AsyncMock(
        return_value=MagicMock(execute=AsyncMock(), fetchall=AsyncMock(return_value=[]))
    )
    yield conn


def _apply_unit_test_mocks():
    """Apply mocks that should only be active during unit test runs.

    Called from pytest_configure when --integration is NOT present.
    """
    # 1. Mock Task Queue / Huey
    _mock_scheduler = _NoOpTaskScheduler()

    import app.infrastructure.queue.factory as _factory_mod

    _factory_mod._scheduler = _mock_scheduler
    _factory_mod.get_scheduler = lambda: _mock_scheduler

    import app.infrastructure.queue.huey_queue as _huey_queue_mod

    _huey_queue_mod.get_huey_scheduler = lambda: _mock_scheduler

    def _noop_shared_task(
        func=None, *, name=None, bind=False, retries=0, retry_delay=0, **options
    ):
        return _mock_scheduler.task(
            func, name=name, bind=bind, retries=retries, retry_delay=retry_delay, **options
        )

    _factory_mod.shared_task = _noop_shared_task
    _huey_queue_mod.shared_task = _noop_shared_task

    # 2. Mock Vector Store
    _mock_vector_store = MagicMock()
    import app.infrastructure.database.vector as _vector_mod

    _vector_mod._vector_store = _mock_vector_store
    _vector_mod.get_vector_store = lambda: _mock_vector_store
    _vector_mod.reset_vector_store = lambda: None

    # 3. Mock Database Resource Manager
    import app.infrastructure.database.resource_manager as _rm_mod

    _rm_mod.db_resource_manager.initialize = AsyncMock()
    _rm_mod.db_resource_manager.shutdown = AsyncMock()
    _rm_mod.db_resource_manager.close = AsyncMock()
    _rm_mod.db_resource_manager.reset = AsyncMock()
    _rm_mod.db_resource_manager.get_raw_connection = _mock_raw_connection
    _rm_mod.db_resource_manager._initialized = True

    # 4. Mock SystemConfigService to avoid DB lookups
    import app.infrastructure.config.service as _config_service_mod

    _config_service_mod.SystemConfigService.get_value = MagicMock(return_value=None)


# =============================================================================
# 5. Mock FinishNode background task to prevent event-loop leaks
# =============================================================================
# _safe_prune launches an asyncio.create_task that outlives the pytest-managed
# event loop, causing aiosqlite thread deadlocks on subsequent tests.
import app.core.engine.nodes.finish as _finish_mod


async def _noop_safe_prune(thread_id: str) -> None:
    pass


_finish_mod._safe_prune = _noop_safe_prune


# =============================================================================
# 6. Defer HookSystem default handlers
# =============================================================================
# setup_default_hooks() imports and registers ~8 handler modules on module load.
# Clearing them after import eliminates side-effects while keeping the system
# introspectable.
import app.core.engine.hooks.core as _hooks_core_mod

_hooks_core_mod.setup_default_hooks = lambda: None
if hasattr(_hooks_core_mod, "hook_system"):
    _hooks_core_mod.hook_system._hooks = {
        event: [] for event in _hooks_core_mod.HookEvent
    }
    _hooks_core_mod.hook_system._prompts = {
        event: [] for event in _hooks_core_mod.HookEvent
    }


# =============================================================================
# 7. Legacy: mock optional heavy dependencies if not installed
# =============================================================================

def _create_mock_modules():
    """Create mock modules for dependencies that may not be installed."""

    # Mock langchain_core - need to create a proper module structure
    # Using MagicMock for submodules
    mock_langchain_core = MagicMock()

    # messages submodule
    mock_langchain_core.messages = MagicMock()
    mock_langchain_core.messages.HumanMessage = MagicMock
    mock_langchain_core.messages.AIMessage = MagicMock
    mock_langchain_core.messages.BaseMessage = MagicMock
    mock_langchain_core.messages.SystemMessage = MagicMock
    mock_langchain_core.messages.ToolMessage = MagicMock
    mock_langchain_core.messages.RemoveMessage = MagicMock

    # runnables submodule
    mock_langchain_core.runnables = MagicMock()
    mock_langchain_core.runnables.RunnableConfig = dict

    # callbacks submodule
    mock_langchain_core.callbacks = MagicMock()
    mock_langchain_core.callbacks.manager = MagicMock()
    mock_langchain_core.callbacks.manager.CallbackManagerForLLMRun = MagicMock

    # outputs submodule
    mock_langchain_core.outputs = MagicMock()
    mock_langchain_core.outputs.ChatResult = MagicMock
    mock_langchain_core.outputs.ChatGeneration = MagicMock
    mock_langchain_core.outputs.Generation = MagicMock
    mock_langchain_core.outputs.LLMResult = MagicMock

    # language_models submodule
    mock_langchain_core.language_models = MagicMock()
    mock_langchain_core.language_models.BaseChatModel = MagicMock
    mock_langchain_core.language_models.LanguageModelInput = MagicMock
    mock_langchain_core.language_models.LanguageModelOutput = MagicMock

    # tools submodule
    mock_langchain_core.tools = MagicMock()

    # Create a proper tool decorator that preserves async functions
    def mock_tool_decorator(*args, **kwargs):
        def decorator(func):
            return func

        # Handle both @tool and @tool() syntax
        if args and callable(args[0]):
            return args[0]
        return decorator

    mock_langchain_core.tools.tool = mock_tool_decorator
    mock_langchain_core.tools.BaseTool = MagicMock
    mock_langchain_core.tools.Tool = MagicMock
    mock_langchain_core.tools.structured_tool = MagicMock()

    # Mock langgraph
    mock_langgraph = MagicMock()
    mock_langgraph.graph = MagicMock()
    mock_langgraph.graph.END = "END"
    mock_langgraph.graph.StateGraph = MagicMock

    # Mock langgraph.graph.message
    mock_graph_message = MagicMock()

    def add_messages_reducer(existing, new):
        """Reducer function for messages."""
        if existing is None:
            existing = []
        if isinstance(new, list):
            return existing + new
        return existing + [new]

    mock_graph_message.add_messages = add_messages_reducer
    mock_langgraph.graph.message = mock_graph_message

    # Mock pgvector
    mock_pgvector = MagicMock()
    mock_pgvector.sqlalchemy = MagicMock()

    # Create a proper Vector class that mimics pgvector.sqlalchemy.Vector
    # It needs to inherit from SQLAlchemy's UserDefinedType to work in mapped_column
    try:
        from sqlalchemy.types import UserDefinedType
        from sqlalchemy.sql.type_api import TypeEngine

        class MockVector(UserDefinedType):
            """Mock pgvector Vector type for testing."""

            def __init__(self, dimensions=None):
                self.dimensions = dimensions

            def get_col_spec(self, **kw):
                return f"VECTOR({self.dimensions})" if self.dimensions else "VECTOR"

            @property
            def python_type(self):
                return list

            def compare_values(self, x, y):
                return x == y

    except ImportError:
        # Fallback if SQLAlchemy is not available
        class MockVector:
            def __init__(self, dimensions=None):
                self.dimensions = dimensions

    mock_pgvector.sqlalchemy.Vector = MockVector

    # Mock pgvector.sqlalchemy
    mock_pgvector_sqlalchemy = MagicMock()
    mock_pgvector_sqlalchemy.Vector = MockVector

    # Mock neo4j
    mock_neo4j = MagicMock()

    # Mock torch
    mock_torch = MagicMock()
    mock_torch.Tensor = MagicMock
    mock_torch.tensor = MagicMock

    # Mock transformers
    mock_transformers = MagicMock()

    # Mock sentence_transformers
    mock_sentence_transformers = MagicMock()

    # Mock celery
    mock_celery = MagicMock()
    mock_celery.Celery = MagicMock
    mock_celery.shared_task = MagicMock

    # Mock jwt (PyJWT)
    mock_jwt = MagicMock()
    mock_jwt.encode = MagicMock(return_value="mock_token")
    mock_jwt.decode = MagicMock(return_value={"sub": "test"})
    mock_jwt.ExpiredSignatureError = Exception
    mock_jwt.InvalidTokenError = Exception

    # Mock tiktoken
    mock_tiktoken = MagicMock()
    mock_tiktoken.encoding_for_model = MagicMock(return_value=MagicMock())
    mock_tiktoken.get_encoding = MagicMock(return_value=MagicMock())

    # Mock langchain_anthropic
    mock_langchain_anthropic = MagicMock()
    mock_langchain_anthropic.ChatAnthropic = MagicMock

    # Mock langchain_openai
    mock_langchain_openai = MagicMock()
    mock_langchain_openai.ChatOpenAI = MagicMock
    mock_langchain_openai.OpenAI = MagicMock
    mock_langchain_openai.OpenAIEmbeddings = MagicMock

    # Mock langchain_community
    mock_langchain_community = MagicMock()
    mock_langchain_community.chat_models = MagicMock()
    mock_langchain_community.chat_models.ChatOllama = MagicMock
    mock_langchain_community.embeddings = MagicMock()
    mock_langchain_community.embeddings.OllamaEmbeddings = MagicMock

    # Register mocks
    sys.modules["langchain_core"] = mock_langchain_core
    sys.modules["langchain_core.messages"] = mock_langchain_core.messages
    sys.modules["langchain_core.runnables"] = mock_langchain_core.runnables
    sys.modules["langchain_core.callbacks"] = mock_langchain_core.callbacks
    sys.modules["langchain_core.callbacks.manager"] = mock_langchain_core.callbacks.manager
    sys.modules["langchain_core.outputs"] = mock_langchain_core.outputs
    sys.modules["langchain_core.language_models"] = mock_langchain_core.language_models
    sys.modules["langchain_core.tools"] = mock_langchain_core.tools
    sys.modules["langchain_core.tools.structured_tool"] = mock_langchain_core.tools.structured_tool
    sys.modules["langgraph"] = mock_langgraph
    sys.modules["langgraph.graph"] = mock_langgraph.graph
    sys.modules[
        "langgraph.graph.message"
    ] = mock_langchain_core.graph.message if hasattr(mock_langchain_core, "graph") else mock_graph_message
    sys.modules["langchain_anthropic"] = mock_langchain_anthropic
    sys.modules["langchain_openai"] = mock_langchain_openai
    sys.modules["langchain_community"] = mock_langchain_community
    sys.modules["langchain_community.chat_models"] = mock_langchain_community.chat_models
    sys.modules["langchain_community.embeddings"] = mock_langchain_community.embeddings
    sys.modules["pgvector"] = mock_pgvector
    sys.modules["pgvector.sqlalchemy"] = mock_pgvector_sqlalchemy
    sys.modules["neo4j"] = mock_neo4j
    sys.modules["torch"] = mock_torch
    sys.modules["transformers"] = mock_transformers
    sys.modules["sentence_transformers"] = mock_sentence_transformers
    sys.modules["jwt"] = mock_jwt
    sys.modules["PyJWT"] = mock_jwt
    sys.modules["tiktoken"] = mock_tiktoken

    # Don't mock celery - tests run in embedded mode and use Huey, not Celery

    return {
        "langchain_core": mock_langchain_core,
        "langgraph": mock_langgraph,
        "pgvector": mock_pgvector,
        "neo4j": mock_neo4j,
    }


# Create mocks at module load time, but only if real packages are not available
_MOCKS = None
try:
    import langchain_core
    import langgraph

    # Real packages available — skip mocking
except ImportError:
    _MOCKS = _create_mock_modules()


import pytest
import logging


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests with real backend implementations (skips unit-test-only mocks)",
    )


def pytest_configure(config):
    """Configure pytest before test collection."""
    if not config.getoption("--integration"):
        _apply_unit_test_mocks()
    else:
        try:
            import app.infrastructure.queue.factory as _factory_mod
            _factory_mod._scheduler = None
        except Exception:
            pass

    # Register default channels (SSE + Mobile) for all test modes
    try:
        from app.core.channel import register_default_channels
        register_default_channels()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def preserve_logging_handlers():
    """Prevent tests from breaking caplog by calling basicConfig()."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    yield
    # Remove any new handlers added during the test
    for handler in list(root.handlers):
        if handler not in original_handlers:
            root.removeHandler(handler)
    # Restore any original handlers that were removed
    for handler in original_handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    # Always reset root level to NOTSET so caplog can capture all levels
    root.setLevel(logging.NOTSET)


def pytest_unconfigure(config):
    """Clean up after test collection."""
    pass
