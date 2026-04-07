# Phase 3 Testing Guide

## Test Coverage

Phase 3 includes comprehensive test coverage for Smart Memory Retrieval:

### Unit Tests

| File | Tests | Coverage |
|------|-------|----------|
| `tests/unit/memory/test_smart_retrieval.py` | 28 tests | Two-stage retrieval, LLM selection, filtering |
| `tests/unit/memory/test_quality.py` | 27 tests | Quality scoring, cleanup recommendations |
| `tests/unit/memory/test_state_tracking.py` | 21 tests | Surface tracking, TTL, cleanup |
| `tests/unit/memory/test_auto_extraction.py` | 15 tests | Auto extraction gates (Phase 2) |

**Total: 91 tests**

### Integration Tests

| File | Tests | Coverage |
|------|-------|----------|
| `tests/integration/test_memory_tools.py` | 12+ tests | Tool integration with smart retrieval |
| `tests/integration/test_smart_retrieval_integration.py` | 10 tests | End-to-end flow |

## Running Tests

### Run All Phase 3 Unit Tests

```bash
cd evoloop/backend

# All unit tests
pytest tests/unit/memory/ -v

# Specific test files
pytest tests/unit/memory/test_smart_retrieval.py -v
pytest tests/unit/memory/test_quality.py -v
pytest tests/unit/memory/test_state_tracking.py -v
```

### Run Integration Tests

```bash
# All memory integration tests
pytest tests/integration/test_memory_tools.py -v -m integration
pytest tests/integration/test_smart_retrieval_integration.py -v -m integration
```

### Using the Test Runner

```bash
# Run all Phase 3 tests
python tests/run_phase3_tests.py

# Verbose mode
python tests/run_phase3_tests.py -v

# Unit tests only
python tests/run_phase3_tests.py --unit

# Integration tests only
python tests/run_phase3_tests.py --int
```

## Test Categories

### Smart Retrieval Tests

```bash
# Test candidate scoring
pytest tests/unit/memory/test_smart_retrieval.py::TestCandidateScoring -v

# Test LLM selection
pytest tests/unit/memory/test_smart_retrieval.py::TestLLMResponseParsing -v

# Test recent tool filtering
pytest tests/unit/memory/test_smart_retrieval.py::TestRecentToolFiltering -v

# Test keyword ranking
pytest tests/unit/memory/test_smart_retrieval.py::TestKeywordRanking -v
```

### Quality Analysis Tests

```bash
# Test freshness scoring
pytest tests/unit/memory/test_quality.py::TestFreshnessScoring -v

# Test usage scoring
pytest tests/unit/memory/test_quality.py::TestUsageScoring -v

# Test specificity scoring
pytest tests/unit/memory/test_quality.py::TestSpecificityScoring -v

# Test cleanup recommendations
pytest tests/unit/memory/test_quality.py::TestCleanupRecommendations -v
```

### State Tracking Tests

```bash
# Test marking surfaced
pytest tests/unit/memory/test_state_tracking.py::TestMarkSurfaced -v

# Test TTL expiration
pytest tests/unit/memory/test_state_tracking.py::TestGetSurfacedIds -v

# Test predictive cache
pytest tests/unit/memory/test_state_tracking.py::TestPredictiveMemoryCache -v
```

## Test Data

Tests use:
- Mock memory entries (no real files)
- Temporary directories for file storage tests
- Monkey-patched settings for isolation
- AsyncMock for LLM calls

## Key Test Scenarios

### 1. Two-Stage Retrieval
```python
# Stage 1: Get candidates
results = await retriever.find_relevant(
    query="Docker deployment",
    context={"recent_tools": []},
)

# Assertions
assert len(results) <= 5
```

### 2. Quality Scoring
```python
scores = await analyzer.analyze_memory(entry)
assert 0 <= scores.freshness <= 1
assert 0 <= scores.overall <= 1
```

### 3. State Tracking
```python
tracker.mark_surfaced("thread_1", ["mem_001"])
assert tracker.is_surfaced("thread_1", "mem_001")
```

## Expected Results

All tests should pass with:
- Python 3.11+
- pytest 7.0+
- pytest-asyncio 0.21+

## Debugging Failed Tests

```bash
# Show full traceback
pytest tests/unit/memory/test_smart_retrieval.py -v --tb=long

# Show local variables
pytest tests/unit/memory/test_smart_retrieval.py -v --showlocals

# Stop on first failure
pytest tests/unit/memory/test_smart_retrieval.py -v -x

# Run specific test
pytest tests/unit/memory/test_smart_retrieval.py::TestCandidateScoring::test_basic_keyword_scoring -v
```

## Continuous Integration

Add to CI pipeline:
```yaml
- name: Run Phase 3 Tests
  run: |
    cd evoloop/backend
    pytest tests/unit/memory/ -v --tb=short
    pytest tests/integration/test_memory_tools.py -v -m integration --tb=short
```

## Test Coverage Report

Generate coverage report:
```bash
cd evoloop/backend
pytest tests/unit/memory/ --cov=app.core.memory --cov-report=html
open htmlcov/index.html
```

## Notes

- Tests use `pytest.mark.asyncio` for async support
- Integration tests marked with `pytest.mark.integration`
- Mock objects prevent external service calls
- Temporary directories ensure clean state
