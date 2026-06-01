#!/usr/bin/env python3
"""
Finish Node Tool Calling E2E Test

This test verifies that the Finish Node (Session Reviewer) successfully
uses tools (e.g. read_file) to audit the worker's output before concluding.
"""

import argparse
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

TEST_PROJECT_ID = 100
TEST_PROJECT_PATH = "/tmp/evoloop_finish_audit_test"
TEST_LOG_FILE = os.path.join(os.path.dirname(__file__), "finish_audit_test.log")
TEST_TIMEOUT = 600

logger = logging.getLogger(__name__)


def _pre_test_cleanup():
    try:
        os.makedirs(os.path.dirname(TEST_LOG_FILE), exist_ok=True)
    except Exception:
        pass

    if os.path.exists(TEST_LOG_FILE):
        os.remove(TEST_LOG_FILE)
        
    os.makedirs(TEST_PROJECT_PATH, exist_ok=True)
    
    test_file = os.path.join(TEST_PROJECT_PATH, "hello.py")
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
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    await _login_and_store_token()
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
    result.inputs["metadata"]["user_id"] = "test-user-1"

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
    parser = argparse.ArgumentParser(description="Finish Node Tool Calling Test")
    parser.add_argument("--timeout", type=int, default=TEST_TIMEOUT)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Finish Node Tool Calling Test")
    logger.info("=" * 60)

    try:
        await _init_backend()
        
        import uuid
        thread_id = f"finish-audit-test-{uuid.uuid4().hex[:6]}"
        
        # Pre-create the file behind the scenes so it exists, but the Worker doesn't know its contents.
        with open(os.path.join(TEST_PROJECT_PATH, "hello.py"), "w") as f:
            f.write("print('BINGO')\n")
        
        prompt = (
            "我已经在 /tmp/evoloop_finish_audit_test/hello.py 中写入了一个秘密字符串。 "
            "你的任务是直接将控制权转交给 Finish Node。 "
            "作为 Worker，你**禁止**使用任何工具（不要读、也不要写）。请直接说任务已就绪，进入审核。"
            "【审核要求】：Finish Node 必须调用 read_file 工具读取该文件，并把里面的秘密字符串写进最终结论中。"
        )
        
        logger.info("\n>>> STARTING AGENT TASK")
        await _run_agent_turn(thread_id, prompt, "Task-1", args.timeout)
        
        logger.info("\n>>> VERIFYING FINISH NODE TOOL CALLING")
        
        from app.infrastructure.database.resource_manager import db_resource_manager
        checkpoint_tuple = await db_resource_manager.checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
        if not checkpoint_tuple:
            raise AssertionError("Checkpointer did not find the thread state.")
            
        state = checkpoint_tuple.checkpoint["channel_values"]
        blackboard = state.get("blackboard")
        if not blackboard:
            raise AssertionError("Blackboard not found in state.")
            
        metadata = blackboard.metadata
        tool_history = metadata.tool_history or []
        
        logger.info(f"Final tool history: {tool_history}")
        
        # Check if the worker created the file
        worker_created = any("worker:write_file" in t or "worker:execute_command" in t for t in tool_history)
        if not worker_created:
            logger.warning("Worker may not have created the file via tool_history, but continuing validation.")
            
        # Verify the Finish node called tools
        finish_tool_calls = [t for t in tool_history if t.startswith("finish:")]
        if not finish_tool_calls:
            logger.error("❌ TEST FAILED: Finish Node did not call any tools to audit the task!")
            sys.exit(1)
            
        logger.info(f"✅ FINISH NODE CALLED TOOLS: {finish_tool_calls}")
        logger.info("✅ TEST COMPLETED SUCCESSFULLY!")

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
