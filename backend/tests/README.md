# EvoLoop Backend Test Suite

Comprehensive test suite for the EvoLoop backend system.

## Quick Start

```bash
# Run all unit tests
pytest tests/unit -v

# Run with coverage
pytest tests/unit --cov=app --cov-report=html

# Run integration tests (requires external services)
pytest tests/integration -m integration -v

# Run specific test file
pytest tests/unit/core/test_context.py -v

# Run with parallel execution
pytest tests/unit -n auto
```

## Test Architecture

```
tests/
├── conftest.py              # Global fixtures and configuration
├── fixtures/                # Test data factories and helpers
│   ├── factories.py         # Object factories
│   └── helpers.py           # Test utilities
├── mocks/                   # Mock implementations
│   ├── llm.py              # LLM mocking
│   ├── memory.py           # Memory mocking
│   └── tools.py            # Tool mocking
├── unit/                    # Unit tests
│   └── core/               # Core module tests
│       ├── test_context.py
│       ├── test_events.py
│       ├── test_tools.py
│       ├── test_memory.py
│       ├── test_learning.py
│       └── test_engine.py
├── integration/             # Integration tests
│   └── test_agent_workflow.py
├── e2e/                     # End-to-end tests
│   └── test_full_workflow.py
├── data/                    # Test data files
│   ├── sample_skill.yaml
│   └── sample_execution_trace.json
└── run_tests.py             # Test runner script
```

## Test Categories

### Unit Tests
- Fast execution (< 100ms per test)
- No external dependencies
- Isolated from other tests
- Location: `tests/unit/`

### Integration Tests
- Test component interactions
- May require databases, cache, etc.
- Marked with `@pytest.mark.integration`
- Location: `tests/integration/`

### E2E Tests
- Full system workflows
- Require complete infrastructure
- Marked with `@pytest.mark.e2e`
- Location: `tests/e2e/`

## Fixtures

### Core Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `evo_context` | Function | Fresh EvoContext instance |
| `context_manager` | Function | ContextManager with test context |
| `agent_state` | Function | Basic AgentState dictionary |
| `execution_ticket` | Function | Sample execution ticket |
| `event_bus` | Function | Fresh event bus instance |
| `memory_manager` | Function | Mocked memory manager |
| `mock_llm_factory` | Function | Factory for mock LLMs |

### Database Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `db_session` | Function | Async database session |
| `db_engine` | Function | SQLAlchemy engine |
| `mock_db_session` | Function | Mock database session |

## Running Tests

### Using pytest directly

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit

# With coverage
pytest --cov=app --cov-report=html

# Parallel execution
pytest -n auto

# Specific marker
pytest -m unit
pytest -m integration
pytest -m "not slow"
```

### Using the test runner

```bash
# Run all tests
python tests/run_tests.py

# Run only unit tests
python tests/run_tests.py --unit

# Run with coverage
python tests/run_tests.py --coverage

# Run in parallel
python tests/run_tests.py --parallel
```

### Using Make

```bash
# Run unit tests
make -f Makefile.test test-unit

# Run with coverage
make -f Makefile.test test-coverage

# Run all tests
make -f Makefile.test test-all
```

## Writing Tests

### Unit Test Example

```python
import pytest
from tests.fixtures.factories import EvoContextFactory

class TestMyFeature:
    """Tests for my feature."""

    def test_basic_functionality(self):
        """Test basic functionality."""
        result = my_function()
        assert result == expected_value

    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test async functionality."""
        result = await my_async_function()
        assert result is not None

    def test_with_context(self, evo_context):
        """Test using fixture."""
        assert evo_context.request_id is not None
```

### Integration Test Example

```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
class TestDatabaseIntegration:
    """Database integration tests."""

    async def test_database_connection(self, db_session):
        """Test database connectivity."""
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

## Test Data

Use factories for creating test data:

```python
from tests.fixtures.factories import (
    EvoContextFactory,
    AgentStateFactory,
    ExecutionTicketFactory,
    MessageFactory,
)

# Create context
ctx = EvoContextFactory.create(user_id="test-user")

# Create agent state
state = AgentStateFactory.with_human_message("Hello")

# Create execution ticket
ticket = ExecutionTicketFactory.for_developer(
    focus_paths=["main.py"],
    acceptance_criteria=["Fix bug"]
)

# Create messages
messages = MessageFactory.conversation(
    "Hello",      # human
    "Hi there",   # AI
    "How are you?",  # human
)
```

## Mocking

### Mock LLM

```python
def test_with_mock_llm(mock_llm_factory):
    """Test with mocked LLM."""
    mock_llm = mock_llm_factory([
        {"content": "First response"},
        {"tool_calls": [{"name": "tool", "args": {}}]},
    ])

    with patch('app.core.llm.factory.LLMFactory.create_llm', return_value=mock_llm):
        result = await my_function()
        assert result is not None
```

### Mock Memory

```python
def test_with_mock_memory(mock_neo4j_memory):
    """Test with mocked Neo4j."""
    mock_neo4j_memory.search_concepts.return_value = [
        MagicMock(name="Concept1", description="Test")
    ]

    result = await search_function()
    assert len(result) == 1
```

## Coverage

Generate coverage reports:

```bash
# HTML report
pytest --cov=app --cov-report=html

# Terminal report
pytest --cov=app --cov-report=term-missing

# XML report (for CI)
pytest --cov=app --cov-report=xml
```

View HTML report: `open htmlcov/index.html`

## CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run Tests
  run: pytest tests/unit -v --cov=app --cov-report=xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Troubleshooting

### Tests failing with database errors

Ensure test database exists:
```bash
createdb evoloop_test
```

### Import errors

Ensure you're in the correct directory and have installed dependencies:
```bash
cd backend
pip install -e ".[dev]"
```

### Async test failures

Ensure `pytest-asyncio` is installed and configured:
```python
pytestmark = pytest.mark.asyncio
```

## Contributing

When adding new tests:

1. Follow the existing naming conventions
2. Add appropriate markers (`@pytest.mark.unit`, etc.)
3. Use fixtures from `conftest.py`
4. Clean up resources after tests
5. Keep unit tests fast (< 100ms)
6. Document complex test scenarios
