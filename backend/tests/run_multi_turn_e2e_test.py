#!/usr/bin/env python3
"""
Universal Code Development — Multi-Turn Memory Integration Test

This test verifies that the LangGraph checkpointer correctly preserves the Agent's
short-term working memory (checkpoints) across multiple distinct conversation turns
within the same thread.

FIXED PARAMETERS:
  - project_id: 99
  - project_path: /tmp/evoloop_multi_turn_test
  - timeout: 600s
"""

import argparse
import asyncio
import logging
import os
import sys
import time

# Basic setup to import EvoLoop modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Temporary project path
TEST_PROJECT_ID = 99
TEST_PROJECT_PATH = "/tmp/evoloop_multi_turn_test"
TEST_LOG_FILE = os.path.join(os.path.dirname(__file__), "multi_turn_e2e_test.log")
TEST_TIMEOUT = 600

logger = logging.getLogger(__name__)


def _pre_test_cleanup():
    try:
        os.makedirs(os.path.dirname(TEST_LOG_FILE), exist_ok=True)
    except Exception:
        pass
    
    if os.path.exists(TEST_LOG_FILE):
        os.remove(TEST_LOG_FILE)
        logger.info(f"[Test] Removed old log: {TEST_LOG_FILE}")
        
    # Setup test workspace
    os.makedirs(TEST_PROJECT_PATH, exist_ok=True)
    with open(os.path.join(TEST_PROJECT_PATH, "dummy_data.txt"), "w") as f:
        f.write("This is a dummy file to verify Turn 1 memory.")


async def _login_and_store_token(username: str = "preterchan", password: str = "hellomylife") -> str:
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning(f"[Test] Initialization had some issues: {e}")

    client = evocloud_manager.api
    login_res = await client.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    logger.info("[Test] Login successful.")
    return token


async def _init_backend():
    from app.infrastructure.database.resource_manager import db_resource_manager
    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    
    await _login_and_store_token()

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken()

    from app.core.engine.graph_builder import GraphBuilder
    from app.core.globals import set_graph
    
    # CRITICAL FIX: The checkpointer MUST be injected into builder.build to prevent amnesia
    builder = GraphBuilder()
    config_path = os.path.join(os.path.dirname(__file__), "../app/core/engine/config/agent_main.yaml")
    workflow = builder.build(os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)
    set_graph(workflow, config_path=os.path.abspath(config_path), checkpointer=db_resource_manager.checkpointer)
    logger.info("[Test] Agent graph built with Checkpointer.")


async def _run_agent_turn(thread_id: str, message: str, turn_name: str, timeout: int) -> str:
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run

    thread_context_store.set_working_directory(thread_id, TEST_PROJECT_PATH)

    logger.info(f"[Test] Dispatching {turn_name} (thread_id={thread_id})...")
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
    result.inputs["metadata"]["user_id"] = "test-user-1"

    logger.info(f"[Test] Running {turn_name} (timeout={timeout}s)...")
    start = time.time()

    try:
        await asyncio.wait_for(
            run_agent_background(thread_id, result.inputs),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        raise RuntimeError(f"Agent timed out after {elapsed:.1f}s")

    elapsed = time.time() - start
    logger.info(f"[Test] {turn_name} completed in {elapsed:.1f}s")
    return thread_id


async def main():
    _pre_test_cleanup()
    parser = argparse.ArgumentParser(description="Code Development Multi-Turn Memory Test")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds")
    args = parser.parse_args()

    sys.stdout = open(TEST_LOG_FILE, "w", buffering=1)
    sys.stderr = sys.stdout
    timeout = args.timeout

    logger.info("=" * 60)
    logger.info("Universal Code Development — Multi-Turn Memory Integration Test")
    logger.info("=" * 60)

    try:
        await _init_backend()
        
        # Ensure unique thread_id for a clean memory test
        import uuid
        thread_id = f"multi-turn-memory-test-{uuid.uuid4().hex[:6]}"
        
        # ---------------------------------------------------------
        # TURN 1
        # ---------------------------------------------------------
        turn_1_msg = (
            "你好，这是一个多轮对话记忆测试的第一轮。请你查看一下当前目录（/tmp/evoloop_multi_turn_test），"
            "找一下有没有什么有意思的文件，并用一句话向我总结你的发现。"
        )
        logger.info("\n>>> STARTING TURN 1")
        await _run_agent_turn(thread_id, turn_1_msg, "Turn-1", timeout)
        
        # ---------------------------------------------------------
        # TURN 2
        # ---------------------------------------------------------
        # In Turn 2, we specifically ask the Agent to recall information 
        # from Turn 1 without restating what the file was.
        turn_2_msg = (
            "这是测试的第二轮。你还记得在上一轮对话中，你在 /tmp/evoloop_multi_turn_test 目录发现了什么文件吗？"
            "请基于你上一轮的总结记忆，在该目录下创建一个名为 memory_test_result.md 的文件，"
            "将你发现的那个文件名写在这个新文件里。"
            "注意：不要去重新用工具探索环境，请直接依赖上一轮对话总结出来的短时记忆（LangGraph State）。"
        )
        logger.info("\n>>> STARTING TURN 2")
        await _run_agent_turn(thread_id, turn_2_msg, "Turn-2", timeout)
        
        # ---------------------------------------------------------
        # VERIFICATION
        # ---------------------------------------------------------
        logger.info("\n>>> VERIFYING MEMORY")
        result_file = os.path.join(TEST_PROJECT_PATH, "memory_test_result.md")
        if not os.path.exists(result_file):
            raise AssertionError(f"Agent did not create the result file: {result_file}")
            
        with open(result_file, "r") as f:
            content = f.read()
            logger.info(f"Result file content:\n{content}")
            
            if "dummy_data.txt" not in content.lower():
                logger.error("❌ TEST FAILED: Agent failed to recall 'dummy_data.txt' from Turn 1 memory.")
                sys.exit(1)
        
        logger.info("✅ MULTI-TURN MEMORY TEST COMPLETED SUCCESSFULLY!")
        logger.info("The Supervisor correctly preserved memory across conversation turns.")

    except AssertionError as e:
        logger.error(f"❌ TEST FAILED (assertion): {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ TEST FAILED (error): {e}")
        sys.exit(1)
    finally:
        logger.info("[Test] Cleaning up resources...")
        from app.infrastructure.database.resource_manager import db_resource_manager
        await db_resource_manager.shutdown()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    asyncio.run(main())
