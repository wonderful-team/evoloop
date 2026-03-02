# EvoLoop Test Suite Architecture

## Overview

This document describes the architecture and design principles of the EvoLoop backend test suite.

## Design Principles

### 1. Test Pyramid

```
       /\
      /  \      E2E Tests (few, slow)
     /----\
    /      \    Integration Tests
   /--------\
  /          \  Unit Tests (many, fast)
 /------------\
```

- **Unit Tests**: 70% of test suite, < 100ms each
- **Integration Tests**: 20% of test suite, < 1s each
- **E2E Tests**: 10% of test suite, seconds to minutes

### 2. Test Isolation

Each test should:
- Run independently
- Not depend on test order
- Clean up after itself
- Use fresh fixtures

### 3. Fast Feedback

- Unit tests should run in seconds
- Parallel execution support
- Selective test running by markers

## Architecture

```
tests/
├── conftest.py              # Global configuration
│   ├── pytest hooks         # Test lifecycle
│   ├── shared fixtures      # Reusable test resources
│   └── test markers         # Categorization
│
├── fixtures/                # Test data factories
│   ├── factories.py         # Object creation
│   └── helpers.py           # Test utilities
│
├── mocks/                   # Mock implementations
│   ├── llm.py              # LLM behavior mocking
│   ├── memory.py           # Memory backend mocks
│   └── tools.py            # Tool execution mocks
│
├── unit/                    # Unit tests
│   └── core/
│       ├── test_context.py      # Context management
│       ├── test_events.py       # Event system
│       ├── test_tools.py        # Tool system
│       ├── test_memory.py       # Memory system
│       ├── test_learning.py     # Learning system
│       └── test_engine.py       # Agent engine
│
├── integration/             # Integration tests
│   └── test_agent_workflow.py   # End-to-end workflows
│
└── e2e/                     # End-to-end tests
    └── test_full_workflow.py    # Complete scenarios
```

## Fixture Hierarchy

```
session scope:
├── event_loop              # Async event loop
└── test_data_dir          # Test data directory

function scope (default):
├── evo_context            # Fresh EvoContext
├── context_manager        # Context management
├── agent_state            # Basic agent state
├── memory_manager         # Mocked memory
├── event_bus              # Fresh event bus
├── mock_llm_factory       # LLM mocking
└── tool_executor          # Tool execution
```

## Test Patterns

### 1. Arrange-Act-Assert

```python
async def test_feature():
    # Arrange
    state = AgentStateFactory.create()
    mock_tool = MockTool.create(return_value="result")

    # Act
    result = await execute(state, tools=[mock_tool])

    # Assert
    assert result["status"] == "success"
    mock_tool.ainvoke.assert_called_once()
```

### 2. Given-When-Then (BDD-style)

```python
async def test_agent_routing():
    # Given: A user request for code
    state = AgentStateFactory.with_human_message("Write Python code")

    # When: The supervisor processes it
    result = await supervisor(state)

    # Then: It should route to developer
    assert result["next_node"] == "developer"
```

### 3. Table-Driven Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "developer"),
    ("research", "deep_researcher"),
    ("document", "documenter"),
])
async def test_routing_decisions(input, expected):
    result = await route(input)
    assert result == expected
```

## Mocking Strategy

### 1. LLM Mocking

```python
# Mock LLM with predefined responses
mock_llm = MockLLMFactory([
    MockLLMResponse(content="I'll help"),
    MockLLMResponse(tool_calls=[{"name": "tool", "args": {}}]),
]).create()

with patch('LLMFactory.create_llm', return_value=mock_llm):
    await function_under_test()
```

### 2. Memory Mocking

```python
# Mock memory backends
mock_memory = MockLongTermMemory()
mock_memory.concepts = [test_concept]

with patch('MemoryManager.long_term', mock_memory):
    result = await search_concepts("query")
```

### 3. Database Mocking

```python
# Use test database with transaction rollback
async with db_session() as session:
    # Test code
    await session.commit()
    # Automatically rolled back after test
```

## Best Practices

### 1. Use Factories

```python
# Good
state = AgentStateFactory.with_human_message("Hello")

# Avoid
state = {
    "messages": [HumanMessage(content="Hello")],
    # ... more setup
}
```

### 2. Assert Specific Behavior

```python
# Good
assert result["next_node"] == "developer"
mock_tool.ainvoke.assert_called_with(expected_args)

# Avoid
assert result is not None
```

### 3. Test Edge Cases

```python
async def test_empty_input():
    """Test with empty input."""
    result = await process("")
    assert result["status"] == "error"

async def test_max_iterations():
    """Test behavior at max iterations."""
    state = AgentStateFactory.create(iteration_count=999)
    result = await process(state)
    assert result["truncated"] is True
```

### 4. Clean Up Resources

```python
@pytest.fixture
async def temp_file():
    path = create_temp_file()
    yield path
    # Cleanup
    path.unlink()
```

## CI/CD Integration

### Running Tests in CI

```yaml
# GitHub Actions example
- name: Unit Tests
  run: pytest tests/unit -v --cov=app --cov-report=xml

- name: Integration Tests
  run: pytest tests/integration -v -m integration
  env:
    POSTGRES_URL: postgresql://localhost/test
    NEO4J_URI: bolt://localhost:7687
```

### Test Reports

```bash
# Generate JUnit XML report
pytest --junitxml=test-results.xml

# Generate coverage report
pytest --cov=app --cov-report=html

# Generate all reports
pytest --cov=app \
       --cov-report=html \
       --cov-report=xml \
       --junitxml=test-results.xml
```

## Performance Testing

```python
@pytest.mark.performance
async def test_agent_response_time(benchmark):
    """Test that agent responds within acceptable time."""
    state = AgentStateFactory.create()

    start = time.time()
    await agent.run(state)
    elapsed = time.time() - start

    assert elapsed < 5.0  # 5 second threshold
```

## Future Improvements

1. **Property-Based Testing**: Use Hypothesis for generative testing
2. **Mutation Testing**: Verify test quality with mutmut
3. **Visual Regression**: For UI components
4. **Load Testing**: For API endpoints
5. **Contract Testing**: Verify API contracts with Pact

## References

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Factory Boy](https://factoryboy.readthedocs.io/)
- [Mock](https://docs.python.org/3/library/unittest.mock.html)
