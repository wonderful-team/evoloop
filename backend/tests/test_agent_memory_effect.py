#!/usr/bin/env python3
"""
E2E Agent Memory Impact Evaluation Test

This test runs the real Agent graph (Supervisor -> Worker -> Finish) on a Python coding task.
It compares:
1. Control Group (Without Memory): The agent is run with no matching memory seeded.
2. Treatment Group (With Memory): A memory entry representing the user's specific coding style
   preferences (Strict Type Annotations, Async DB operations, test_async_ test prefixes) is seeded.
We verify the output code generated in both runs to evaluate the direct impact of memory on the Agent's output.
"""

import asyncio
import logging
import os
import sys
import shutil

# Basic setup to import EvoLoop modules
backend_dir = "/Users/xujin/Projects/develop-assistant.cn/evoloop/backend"
sys.path.insert(0, backend_dir)

# Dedicated test paths
TEST_DATA_DIR = "/tmp/evoloop_agent_memory_test_data"
TEST_PROJECT_PATH = "/tmp/agent_memory_test_project"

os.environ["EVOLOOP_APP_DATA_DIR"] = TEST_DATA_DIR
os.environ["EMBEDDED_MODE"] = "True"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AgentMemoryEval")


def cleanup_paths():
    for p in [TEST_DATA_DIR, TEST_PROJECT_PATH]:
        if os.path.exists(p):
            try:
                shutil.rmtree(p)
            except Exception:
                pass
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(TEST_DATA_DIR, "database"), exist_ok=True)
    os.makedirs(TEST_PROJECT_PATH, exist_ok=True)


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


async def init_backend():
    from app.infrastructure.database.resource_manager import db_resource_manager
    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=True, seed_data=False)

    await _login_and_store_token()

    from app.core.environment import awaken
    logger.info("[Test] Awakening agent environment...")
    await awaken()

    from app.core.events.discovery import auto_discover_handlers
    auto_discover_handlers()

    # Query and set default platform model dynamically
    from app.infrastructure.llm.platform_service import get_available_llm_models
    from app.infrastructure.config.service import SystemConfigService
    SystemConfigService.set_value("LLM_CONFIG_TYPE", "platform")
    SystemConfigService.set_value("LLM_BASE_URL", "")
    SystemConfigService.set_value("LLM_API_KEY", "")
    models = await get_available_llm_models("platform")
    logger.info(f"[Test] Available platform models: {models}")
    if models:
        selected_model = models[0]["id"]
        for m in models:
            mid = m["id"]
            if "kimi" in mid.lower() or "gpt-4o" in mid.lower() or "deepseek" in mid.lower():
                selected_model = mid
                break
        SystemConfigService.set_value("LLM_MODEL", selected_model)
        logger.info(f"[Test] Dynamically set default LLM_MODEL to: {selected_model}")
    else:
        SystemConfigService.set_value("LLM_MODEL", "gpt-4o")
        logger.warning("[Test] No platform models found, falling back to gpt-4o")

    # Set up the Agent Graph
    from app.core.globals import init_agent_graph
    init_agent_graph()
    logger.info("[Test] Agent graph initialized.")


async def run_agent_workflow(thread_id: str, user_id: str, project_id: int, goal_prompt: str):
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.sub_schemas import BlackboardState
    from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket, TicketParameters

    # Clean workspace folder
    if os.path.exists(TEST_PROJECT_PATH):
        shutil.rmtree(TEST_PROJECT_PATH)
    os.makedirs(TEST_PROJECT_PATH, exist_ok=True)

    thread_context_store.set_working_directory(thread_id, TEST_PROJECT_PATH)

    logger.info(f"[Test] Dispatching agent run for thread={thread_id}...")
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=goal_prompt,
        project_id=project_id,
        goal_prefix="[Memory E2E Test] ",
        skip_message_persistence=False
    )

    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    # Set up worker parameters and authorized tools
    system_instructions = (
        "You are a professional software engineer. "
        "Write the code accurately based on the prompt instructions and the project memory context."
    )
    blackboard = BlackboardState(
        ticket=ExecutionTicket(
            ticket_type="task",
            topic="Write Repository Code",
            agent_config=AgentRuntimeConfig(
                role_name="Worker",
                system_instructions=system_instructions,
                tools=["read_file", "write_file", "grep_search", "list_dir"],
            ),
            parameters=TicketParameters(),
        )
    )
    result.inputs["blackboard"] = blackboard.model_dump(mode="json")
    
    if "metadata" not in result.inputs:
        result.inputs["metadata"] = {}
    result.inputs["metadata"]["user_id"] = user_id
    result.inputs["metadata"]["project_id"] = project_id
    result.inputs["metadata"]["skip_persistence"] = False

    logger.info(f"[Test] Starting agent background thread execution...")
    # Timeout after 10 minutes to prevent hangs
    await asyncio.wait_for(
        run_agent_background(thread_id, result.inputs),
        timeout=600.0
    )
    logger.info(f"[Test] Agent execution complete for thread={thread_id}.")


def evaluate_generated_code(file_path: str) -> dict:
    """Evaluate if the generated file complies with the memory styling guidelines."""
    if not os.path.exists(file_path):
        return {"file_exists": False, "compliance_score": 0, "findings": ["File user_repo.py was not created."]}

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    findings = []
    points = 0
    max_points = 3

    # Check 1: Strict Type Annotations
    # Expect return types like -> or parameter annotations like : in functions
    if "->" in content and ":" in content:
        points += 1
        findings.append("✓ Strictly used Python Type Annotations.")
    else:
        findings.append("✗ Missing Type Annotations in function signatures.")

    # Check 2: Async DB operations
    if "async def" in content:
        points += 1
        findings.append("✓ Implemented asynchronous database calls (async/await).")
    else:
        findings.append("✗ Synchronous database calls used instead of async.")

    # Check 3: test_async_pref_ prefix for test functions
    test_functions = [line.strip() for line in content.splitlines() if "def test" in line]
    if test_functions:
        async_prefixed = [tf for tf in test_functions if "def test_async_pref_" in tf]
        if len(async_prefixed) == len(test_functions):
            points += 1
            findings.append(f"✓ All test cases ({len(test_functions)}) correctly prefixed with test_async_pref_.")
        else:
            findings.append(f"✗ Test cases mismatch: {len(async_prefixed)}/{len(test_functions)} used test_async_pref_ prefix.")
    else:
        findings.append("✗ No test functions detected in the code.")

    score = int((points / max_points) * 100)
    return {
        "file_exists": True,
        "compliance_score": score,
        "findings": findings,
        "code": content
    }


async def main():
    cleanup_paths()
    await init_backend()

    goal_prompt = (
        "Please write a Python repository method for retrieving a User by ID from the database, and write its unit test. "
        "Write the code directly to a file named 'user_repo.py' in the current workspace CWD. "
        "Do NOT do anything else. Return only a brief plain-text confirmation when done."
    )

    # -------------------------------------------------------------
    # RUN 1: Without Memory (Control Group)
    # -------------------------------------------------------------
    logger.info("\n" + "="*50 + "\nRUNNING CONTROL GROUP: WITHOUT MEMORY\n" + "="*50)
    # We use a user ID that has no seeded memories
    try:
        await run_agent_workflow(
            thread_id="thread_control_no_memory",
            user_id="control_user_xyz",
            project_id=99,
            goal_prompt=goal_prompt
        )
        control_eval = evaluate_generated_code(os.path.join(TEST_PROJECT_PATH, "user_repo.py"))
    except Exception as e:
        logger.exception(f"Control run failed: {e}")
        control_eval = {"file_exists": False, "compliance_score": 0, "findings": [f"Control run error: {e}"]}

    # -------------------------------------------------------------
    # Seed Style Preference Memory for Treatment Group
    # -------------------------------------------------------------
    from app.core.memory.lifespan import MemoryLifespanManager
    container = MemoryLifespanManager.get_container()
    manager = container.memory_manager
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel

    logger.info("[Test] Seeding style preference memory entry...")
    style_preference_mem = MemoryEntry(
        title="Python Code Style and Async Naming Preference",
        description="Strictly use Python type annotations for all function definitions, use async/await for all database operations, and prefix all test function names with test_async_pref_ instead of test_async_.",
        content="User coding preferences: 1. Always write type annotations. 2. Write async/await for database calls. 3. Prefix test functions with test_async_pref_.",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.PRIVATE,
        project_id=99,
        user_id="test_user_456"
    )
    await manager.save_memory(style_preference_mem)
    # Refresh MEMORY.md
    await container.two_tier_manager.regenerate_memory_md()

    # -------------------------------------------------------------
    # RUN 2: With Memory (Treatment Group)
    # -------------------------------------------------------------
    logger.info("\n" + "="*50 + "\nRUNNING TREATMENT GROUP: WITH MEMORY\n" + "="*50)
    # We use the user ID that matches the seeded style preference memory
    try:
        await run_agent_workflow(
            thread_id="thread_treatment_with_memory",
            user_id="test_user_456",
            project_id=99,
            goal_prompt=goal_prompt
        )
        treatment_eval = evaluate_generated_code(os.path.join(TEST_PROJECT_PATH, "user_repo.py"))
    except Exception as e:
        logger.exception(f"Treatment run failed: {e}")
        treatment_eval = {"file_exists": False, "compliance_score": 0, "findings": [f"Treatment run error: {e}"]}

    # -------------------------------------------------------------
    # REPORTING & ASSERTS
    # -------------------------------------------------------------
    logger.info("\n\n" + "="*30 + " AGENT E2E MEMORY IMPACT REPORT " + "="*30)
    print(f"\n- **Control Group (Without Memory)**:")
    print(f"  - File Created: {control_eval['file_exists']}")
    print(f"  - Compliance Score: {control_eval['compliance_score']}%")
    for f in control_eval['findings']:
        print(f"    - {f}")
    if control_eval.get('code'):
        print(f"    - Code Snippet:\n```python\n{control_eval['code'][:300]}\n```")

    print(f"\n- **Treatment Group (With Memory)**:")
    print(f"  - File Created: {treatment_eval['file_exists']}")
    print(f"  - Compliance Score: {treatment_eval['compliance_score']}%")
    for f in treatment_eval['findings']:
        print(f"    - {f}")
    if treatment_eval.get('code'):
        print(f"    - Code Snippet:\n```python\n{treatment_eval['code'][:300]}\n```")

    improvement = treatment_eval['compliance_score'] - control_eval['compliance_score']
    print(f"\n- **Memory Compliance Improvement**: +{improvement}%")
    print("="*80)

    # Cleanup backend
    from app.infrastructure.database.resource_manager import db_resource_manager
    await db_resource_manager.shutdown()
    
    # Assertions to verify overall memory effect
    assert treatment_eval['file_exists'], "Treatment run failed to write user_repo.py"
    assert treatment_eval['compliance_score'] > control_eval['compliance_score'], \
        f"Memory had no impact: Treatment compliance ({treatment_eval['compliance_score']}%) <= Control compliance ({control_eval['compliance_score']}%)"
    assert treatment_eval['compliance_score'] == 100, f"Treatment did not achieve 100% compliance: {treatment_eval['compliance_score']}%"
    
    logger.info("🎉 E2E Agent Memory Impact Evaluation Test passed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
