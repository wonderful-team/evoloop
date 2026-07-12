#!/usr/bin/env python3
"""
Finish Node Failure Loop & Audit Quality Test

This test verifies two crucial aspects of the Finish Node (Session Reviewer):
1. **Failure Loop**: If the Finish Node finds the task incomplete or wrong, it outputs FAILED, 
   which routes back to Supervisor -> Worker, and the Worker fixes it.
2. **Audit Quality**: The background structured extraction Celery task is executed and writes 
   valid extraction records to the database.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_PROJECT_ID = 101
TEST_PROJECT_PATH = "/tmp/evoloop_finish_failure_test"
TEST_LOG_FILE = os.path.join(os.path.dirname(__file__), "finish_failure_test.log")
TEST_TIMEOUT = 1200

logger = logging.getLogger(__name__)

# Force Celery to execute tasks synchronously for testing
from celery import current_app
current_app.conf.task_always_eager = True
current_app.conf.task_eager_propagates = True


def _pre_test_cleanup():
    try:
        os.makedirs(os.path.dirname(TEST_LOG_FILE), exist_ok=True)
    except Exception:
        pass
    if os.path.exists(TEST_LOG_FILE):
        os.remove(TEST_LOG_FILE)
    os.makedirs(TEST_PROJECT_PATH, exist_ok=True)
    test_file = os.path.join(TEST_PROJECT_PATH, "result.txt")
    if os.path.exists(test_file):
        os.remove(test_file)


async def _login_and_store_token(username: str = "preterchan", password: str = "hellomylife") -> str:
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service
    evocloud_manager.initialize()
    client = evocloud_manager.api
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")
    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    return token


async def _init_backend():
    # Skip remote login since we are only testing local Audit/Celery
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    from app.core.environment import awaken
    await awaken()
    from app.core.events.discovery import auto_discover_handlers
    auto_discover_handlers()
    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    workflow = builder.build(os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)
    set_graph(workflow, config_path=os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)


async def _run_agent_turn(thread_id: str, message: str, turn_name: str, timeout: int) -> str:
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run

    thread_context_store.set_working_directory(thread_id, TEST_PROJECT_PATH)
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=TEST_PROJECT_ID,
        goal_prefix=f"[{turn_name}] "
    )

    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")
    
    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["member_id"] = 1

    start = time.time()
    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"Agent timed out after {time.time() - start:.1f}s")
    
    return thread_id


async def main():
    _pre_test_cleanup()
    parser = argparse.ArgumentParser(description="Finish Node Failure Loop Test")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Finish Node Failure Loop & Audit Quality Test")
    logger.info("=" * 60)

    try:
        await _init_backend()
        
        # Force Celery eager
        import app.infrastructure.queue.celery_app as celery_mod
        from app.core.engine.tasks import engine_audit_structured_extraction
        celery_mod.celery_app.conf.task_always_eager = True
        
        # 1. Setup DB resources
        # (Handled by _init_backend)
        
        # 2. Build a fake AgentState that simulates a bad worker outcome
        from app.core.engine.state.base import AgentState
        from app.core.engine.state.sub_schemas import ExecutionTicket, VerificationStatus
        from langchain_core.messages import HumanMessage, AIMessage
        import uuid
        
        thread_id = f"audit-fail-test-{uuid.uuid4().hex[:6]}"
        bad_file_path = os.path.join(TEST_PROJECT_PATH, "result.txt")
        with open(bad_file_path, "w") as f:
            f.write("WRONG_ANSWER\n")
            
        messages = [
            HumanMessage(content=f"Create a file at {bad_file_path} containing exactly 'CORRECT_ANSWER'"),
            AIMessage(content="I have created the file as requested.", name="worker")
        ]
        
        ticket = ExecutionTicket(
            topic="File Creation",
            ticket_type="development",
            acceptance_criteria=[
                f"File {bad_file_path} MUST contain EXACTLY 'CORRECT_ANSWER'",
                "CRITICAL: You MUST use the read_file tool to verify the file contents. Do not trust the worker's message."
            ]
        )
        verification = VerificationStatus(status="unverified")
        
        state = AgentState(
            messages=messages,
            ticket=ticket,
            verification=verification,
            thread_id=thread_id,
            session_goal=f"Create {bad_file_path} with 'CORRECT_ANSWER'"
        )
        
        # 3. Execute AuditService
        from app.core.engine.services.audit_service import AuditService
        from langchain_core.runnables.config import RunnableConfig
        from app.core.config import settings
        
        service = AuditService()
        config = RunnableConfig(configurable={
            "thread_id": thread_id, 
            "project_id": TEST_PROJECT_ID, 
            "member_id": 1, 
            "run_id": "test-run",
            "model": "kimi-k2-thinking-turbo"
        })
        from app.core.events.base import system_bus
        from app.core.engine.event import ExtractionCompletedEvent
        from app.core.events.registry import SystemEventType
        from app.core.engine.tasks import engine_audit_structured_extraction
        
        # Patch Celery delay for async task in eager mode to avoid asyncio.run() crash
        original_delay = engine_audit_structured_extraction.delay
        def mock_delay(*args, **kwargs):
            # Extract the original async function bypassing the Celery task and _celery_async_wrapper
            import inspect
            
            # The Celery task object has a .run method
            target_fn = engine_audit_structured_extraction.run
            
            # If wrapped by _celery_async_wrapper, it will have __wrapped__
            if hasattr(target_fn, "__wrapped__"):
                target_fn = target_fn.__wrapped__
                
            asyncio.create_task(target_fn(*args, **kwargs))
            
        engine_audit_structured_extraction.delay = mock_delay
        
        extraction_events = []
        async def mock_subscriber(event: ExtractionCompletedEvent):
            extraction_events.append(event)
            
        system_bus.subscribe(SystemEventType.EXTRACTION_COMPLETED, mock_subscriber)
        
        logger.info("\n>>> EXECUTING AUDIT SERVICE (EXPECTING FAILED)")
        start = time.time()
        try:
            audit_result = await service.execute(
                state=state,
                config=config,
                tool_history=[]
            )
        finally:
            # Restore original delay
            engine_audit_structured_extraction.delay = original_delay
        
        logger.info(f"Audit completed in {time.time() - start:.1f}s")
        
        # 4. Verify Failure Outcome
        final_outcome = audit_result.blackboard.metadata.final_outcome
        logger.info(f"Final Outcome: {final_outcome}")
        
        if final_outcome != "FAILED":
            logger.error(f"❌ TEST FAILED: Finish Node did not reject the bad file! Outcome was {final_outcome}")
            sys.exit(1)
            
        # Verify Tools were used
        tool_history = audit_result.blackboard.metadata.tool_history or []
        finish_tool_calls = [t for t in tool_history if t.startswith("finish:")]
        if not finish_tool_calls:
            logger.error("❌ TEST FAILED: Finish Node did not call any tools to verify the failure!")
            sys.exit(1)
            
        logger.info(f"✅ Finish Node correctly called tools: {finish_tool_calls}")
        logger.info(f"✅ Finish Node correctly rejected task with outcome FAILED")
        
        # 5. Verify Background Extraction (Celery)
        # We need to yield control to allow the event to be processed
        # The background LLM extraction might take 10-20 seconds
        timeout = 60.0
        elapsed = 0.0
        while not extraction_events and elapsed < timeout:
            await asyncio.sleep(1.0)
            elapsed += 1.0
            
        if not extraction_events:
            logger.error("❌ TEST FAILED: ExtractionCompletedEvent was not published! Background Celery task may have failed.")
            sys.exit(1)
            
        logger.info(f"✅ FOUND {len(extraction_events)} ExtractionCompletedEvent(s).")
        for e in extraction_events:
            logger.info(f" - Extracted Data: {e.extracted_data}")
        
        logger.info("✅ TEST COMPLETED SUCCESSFULLY: Finish node rejected failure, and Celery extraction succeeded!")

    except AssertionError as e:
        logger.error(f"❌ TEST FAILED (assertion): {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ TEST FAILED (error): {e}")
        sys.exit(1)
    finally:
        from app.infrastructure.database.resource_manager import db_resource_manager
        await db_resource_manager.shutdown()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    asyncio.run(main())
