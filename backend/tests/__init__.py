"""
EvoLoop Backend Test Suite

Test Organization:
- unit/: Unit tests for individual modules (no external dependencies)
- integration/: Integration tests (with database, cache, etc.)
- e2e/: End-to-end tests (full system workflow)
- fixtures/: Shared test fixtures and utilities
- mocks/: Mock implementations for external services
- data/: Test data files

Usage:
    # Run all tests
    pytest

    # Run specific test types
    pytest -m unit
    pytest -m integration
    pytest -m e2e

    # Run with coverage
    pytest --cov=app --cov-report=html

    # Run parallel tests
    pytest -n auto
"""

__version__ = "1.0.0"
