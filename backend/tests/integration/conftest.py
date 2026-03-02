"""
Integration test configuration.
"""
import pytest


@pytest.fixture(scope="function")
def event_loop():
    """Create a fresh event loop for each test."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
