"""
Wiki Agent Unit Tests

These tests are designed for Embedded Mode (LocalCelery) and do not require:
- Redis server
- Celery worker process
- External task queue

All tasks run in-process using asyncio.
"""
