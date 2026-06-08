#!/usr/bin/env python3
"""
Test real LLM connectivity through the full EvoLoop backend stack.

This script:
1. Logs into the EvoCloud platform
2. Triggers a background agent run
3. Verifies the 429 rate-limit handling fix

Usage:
    cd /path/to/evoloop
    arch -arm64 python3 deploy/test_real_llm.py
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime

# ── Bootstrap paths ──────────────────────────────────────────────────────────
BACKEND_ROOT = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, os.path.abspath(BACKEND_ROOT))

# Load root .env so EVOCLOUD_API_URL / EVOCLOUD_WS_URL are available
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Mock lancedb / pyarrow (architecture mismatch on this Mac)
from unittest import mock
sys.modules["lancedb"] = mock.MagicMock()
_pa_mock = mock.MagicMock()
_pa_mock.__version__ = "15.0.0"
sys.modules["pyarrow"] = _pa_mock
for sub in ["compute", "parquet", "types", "dataset", "csv", "json", "flight", "ipc"]:
    sys.modules[f"pyarrow.{sub}"] = mock.MagicMock()
sys.modules["neo4j"] = mock.MagicMock()

# Mock document_reader to avoid pandas/pyarrow import chain
_doc_reader_mock = mock.MagicMock()
_doc_reader_mock.document_reader_service = mock.MagicMock()
_doc_reader_mock.document_reader_service.read_document = mock.AsyncMock(return_value="")
sys.modules["app.core.file.document_reader"] = _doc_reader_mock

# ── Environment (embedded mode = SQLite + FileCache + Huey) ──────────────────
os.environ["EMBEDDED_MODE"] = "true"
os.environ["SQLITE_DB_PATH"] = "/tmp/evoloop_test.db"
os.environ["CHECKPOINTER_DATABASE_URI"] = "sqlite+aiosqlite:///tmp/evoloop_test.db"
os.environ["PYTHONUNBUFFERED"] = "1"
# Ensure defaults are set only when env vars are missing
os.environ.setdefault("EVOCLOUD_API_URL", "http://127.0.0.1")
os.environ.setdefault("EVOCLOUD_WS_URL", "ws://127.0.0.1/gateway/ws")

# Verbose logging so we can watch the 429 handling in real time
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_real_llm")


async def main():
    # ── Lazy imports (modules touch DB on import) ───────────────────────────
    logger.info("Importing backend modules...")
    from app.core.config import settings
    from app.core.evocloud import evocloud_manager
    from app.core.engine.background_agent import run_agent_background, BackgroundAgentInputs
    from app.infrastructure.cache import cache

    logger.info(f"EVOCLOUD_API_URL = {settings.EVOCLOUD_API_URL}")
    logger.info(f"EMBEDDED_MODE    = {settings.EMBEDDED_MODE}")

    # ── Initialize Graph (normally done in FastAPI lifespan) ────────────────
    logger.info("Initializing database & graph...")
    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    import os

    await db_resource_manager.initialize(create_tables=True, seed_data=True)
    checkpointer = db_resource_manager.checkpointer

    builder = GraphBuilder()
    config_path = os.path.join(BACKEND_ROOT, "app", "core", "engine", "config", "agent_main.yaml")
    graph = builder.build(config_path, checkpointer=checkpointer)
    set_graph(graph, config_path=config_path, checkpointer=checkpointer)
    logger.info("Graph initialized.")

    # ── Seed systemconfig (needed by i18n / SystemConfigService) ────────────
    logger.info("Seeding systemconfig...")
    try:
        from app.infrastructure.database.sql.database import session_scope
        from app.models import SystemConfig
        async with session_scope() as session:
            for key, val in [
                ("LANGUAGE", "zh"),
                ("DEFAULT_PROJECT_ID", "43"),
            ]:
                existing = await session.get(SystemConfig, key)
                if not existing:
                    session.add(SystemConfig(key=key, value=val))
        logger.info("SystemConfig seeded.")
    except Exception as e:
        logger.warning(f"SystemConfig seeding failed (may already exist): {e}")

    # ── Login ───────────────────────────────────────────────────────────────
    username = "preterchan"
    password = os.environ.get("EVOLOOP_PASSWORD") or input("Password for preterchan: ")

    logger.info(f"Logging in as {username}...")
    login_result = await evocloud_manager.login(username, password)
    if not login_result.success:
        logger.error(f"Login failed: {login_result.message}")
        sys.exit(1)

    token = evocloud_manager.get_token()
    logger.info(f"Login OK — token prefix: {token[:24]}...")

    # Set active model so LLMFactory has a fallback when config.model is None
    from app.core.context.manager import ContextManager
    ctx = ContextManager.current()
    ctx.active_model = "claude-3-5-sonnet-20240620"
    logger.info(f"Active model set to: {ctx.active_model}")

    # ── Subscribe to Redis events so we see frontend notifications ──────────
    event_channel = None
    received_events = []

    async def event_listener():
        nonlocal event_channel
        from app.infrastructure.cache.abstract import PubSubBackend
        ps: PubSubBackend = cache.pubsub()
        event_channel = f"chat:test-thread-events:{uuid.uuid4().hex[:6]}"
        # We can't easily subscribe to the real channel (thread_id is dynamic),
        # but we can poll the DB after the run.  For now just log.
        logger.info("Event listener stub ready (DB polling will be used)")

    # ── Trigger agent run ───────────────────────────────────────────────────
    thread_id = f"test-{datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
    project_id = 43
    goal = "Say hello and confirm the LLM connection is working. Keep it under 20 words."

    logger.info("=" * 60)
    logger.info(f"Triggering agent run")
    logger.info(f"  thread_id  = {thread_id}")
    logger.info(f"  project_id = {project_id}")
    logger.info(f"  goal       = {goal}")
    logger.info("=" * 60)

    inputs = BackgroundAgentInputs(
        messages=[{"type": "human", "content": goal}],
        project_id=project_id,
        goal=goal,
        model="kimi-k2-thinking-turbo",
    )

    start = asyncio.get_event_loop().time()
    try:
        await run_agent_background(thread_id, inputs)
    except Exception as e:
        logger.exception(f"Agent run crashed: {e}")
        # Even on crash, check the DB for any persisted error messages
    finally:
        elapsed = asyncio.get_event_loop().time() - start
        logger.info(f"Run finished in {elapsed:.1f}s")

    # ── Inspect final state ─────────────────────────────────────────────────
    logger.info("Inspecting final checkpoint state...")
    from app.core.globals import get_graph

    graph = get_graph()
    if graph:
        config = {"configurable": {"thread_id": thread_id}}
        try:
            final_state = await graph.aget_state(config)
            if final_state and final_state.values:
                msgs = final_state.values.get("messages", [])
                logger.info(f"Final state contains {len(msgs)} messages")
                for i, m in enumerate(msgs):
                    role = getattr(m, "type", "?")
                    content = str(getattr(m, "content", ""))[:120]
                    is_err = getattr(m, "metadata", {}).get("is_error", False)
                    logger.info(f"  [{i}] {role} is_error={is_err}: {content}")
            else:
                logger.warning("No final state values found")
        except Exception as e:
            logger.warning(f"Could not read final state: {e}")
    else:
        logger.warning("Graph not initialized — skipping state inspection")

    # ── Inspect DB for persisted messages ───────────────────────────────────
    logger.info("Inspecting database for persisted messages...")
    try:
        from app.infrastructure.database.sql.database import session_scope
        from app.models import Message as DBMessage
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = (
                select(DBMessage)
                .where(DBMessage.thread_id == thread_id)
                .order_by(DBMessage.sequence_number)
            )
            result = await session.execute(stmt)
            db_msgs = result.scalars().all()
            logger.info(f"DB contains {len(db_msgs)} messages for this thread")
            for m in db_msgs:
                content = (m.content or "")[:120]
                logger.info(
                    f"  [seq={m.sequence_number}] role={m.role} "
                    f"action={m.action_type}: {content}"
                )
    except Exception as e:
        logger.warning(f"DB inspection failed: {e}")

    # ── Cleanup ─────────────────────────────────────────────────────────────
    logger.info("Cleaning up connections...")
    try:
        await evocloud_manager.stop()
        logger.info("EvoCloud manager stopped.")
    except Exception as e:
        logger.warning(f"EvoCloud stop failed: {e}")

    try:
        from app.infrastructure.database.resource_manager import db_resource_manager
        await db_resource_manager.shutdown()
        logger.info("DB resources shut down.")
    except Exception as e:
        logger.warning(f"DB shutdown failed: {e}")

    logger.info("Test complete.")


if __name__ == "__main__":
    asyncio.run(main())
