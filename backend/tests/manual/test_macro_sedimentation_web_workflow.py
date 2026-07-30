#!/usr/bin/env python3
"""Macro Creation — Web Workflow (10+ steps) Manual Test with Real LLM.

Runs the complete macro creation flywheel with a real Agent engine and
real LLM.  The agent is asked to interact with a locally served web form using
browser_control.  The resulting macro should contain at least 10 deterministic
web automation steps.

Usage:
    .venv/bin/python tests/manual/test_macro_sedimentation_web_workflow.py
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import logging
import os
import socket
import socketserver
import sys
import tempfile
import threading
import time

os.environ.setdefault("EMBEDDED_MODE", "True")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sqlalchemy import select

from app.core.events.base import system_bus
from app.core.execution.macro.event.subscribers import MacroSedimentationSubscriber
from app.core.execution.macro.schemas import MacroActionType, MacroScript, MacroStepType
from app.infrastructure.database import session_scope
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models import AgentActivity, Macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("macro_creation_web_workflow")

TEST_TIMEOUT = 300
MIN_STEPS = 10

HTML_FORM = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Web Macro Test Form</title>
    <style>
        body { font-family: sans-serif; padding: 2rem; max-width: 600px; margin: 0 auto; }
        label { display: inline-block; width: 100px; margin-top: 10px; }
        input { width: 250px; padding: 5px; margin-top: 10px; }
        button { margin-top: 15px; padding: 8px 16px; cursor: pointer; }
        #result { margin-top: 20px; padding: 15px; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <h1>Contact Form</h1>
    <form id="contactForm">
        <label for="username">Username:</label>
        <input type="text" id="username" name="username" placeholder="Enter username"><br>
        <label for="email">Email:</label>
        <input type="email" id="email" name="email" placeholder="Enter email"><br>
        <button type="button" id="submit">Submit</button>
        <button type="button" id="reset">Reset</button>
    </form>
    <div id="result" role="status" style="margin-top: 20px; padding: 15px; border: 1px solid #ccc;">
        <h2>Result</h2>
        <p id="resultText">No submission yet</p>
    </div>
    <script>
        document.getElementById('submit').addEventListener('click', function() {
            var username = document.getElementById('username').value;
            var email = document.getElementById('email').value;
            document.getElementById('resultText').textContent = 'User: ' + username + ', Email: ' + email;
        });
        document.getElementById('reset').addEventListener('click', function() {
            document.getElementById('contactForm').reset();
            document.getElementById('resultText').textContent = 'No submission yet';
        });
    </script>
</body>
</html>
"""


async def _login_and_store_token(
    username: str = "preterchan", password: str = "hellomylife"
) -> int:
    """Login via EvoCloud manager and store token in IdentityStore."""
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    logger.info("[Test] Initializing EvoCloud Manager...")
    try:
        evocloud_manager.initialize()
    except Exception as e:
        logger.warning("[Test] Initialization had some issues: %s", e)

    logger.info("[Test] Logging in via EvoCloud as %s...", username)
    login_res = await evocloud_manager.login(username, password)
    if not login_res.get("success"):
        raise RuntimeError(f"Login failed: {login_res}")

    token = login_res["token"]
    refresh_token = login_res.get("refresh_token", "")
    await identity_service.set_token(token, refresh_token)
    member_id = await identity_service.get_member_id(token)
    logger.info("[Test] Login successful. member_id=%s", member_id)
    return member_id


async def _init_backend() -> None:
    """Initialize the real database, agent graph, and LLM platform."""
    from app.infrastructure.config.service import SystemConfigService

    logger.info("[Test] Initializing database...")
    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    logger.info("[Test] Database initialized.")

    logger.info("[Test] Initializing agent graph...")
    from app.core.globals import init_agent_graph

    init_agent_graph()
    logger.info("[Test] Agent graph ready.")

    logger.info("[Test] Configuring LLM platform...")
    SystemConfigService.set_value("LLM_CONFIG_TYPE", "platform")
    SystemConfigService.set_value("LLM_BASE_URL", "")
    SystemConfigService.set_value("LLM_API_KEY", "")

    from app.infrastructure.llm.platform_service import get_available_llm_models

    models = await get_available_llm_models("platform")
    logger.info("[Test] Available platform models: %s", models)
    if models:
        selected_model = models[0]["id"]
        for m in models:
            mid = m["id"]
            if (
                "kimi" in mid.lower()
                or "gpt-4o" in mid.lower()
                or "deepseek" in mid.lower()
            ):
                selected_model = mid
                break
        SystemConfigService.set_value("LLM_MODEL", selected_model)
        logger.info("[Test] Selected LLM_MODEL: %s", selected_model)
    else:
        SystemConfigService.set_value("LLM_MODEL", "gpt-4o")
        logger.warning("[Test] No platform models found, falling back to gpt-4o")


def _find_free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def _start_static_server(directory: str, port: int) -> socketserver.TCPServer:
    """Start a threaded HTTP server serving ``directory`` on ``port``."""
    os.chdir(directory)
    httpd = socketserver.TCPServer(("", port), _QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    logger.info("[Test] Static server started on http://localhost:%d", port)
    return httpd


async def _run_agent(
    thread_id: str, member_id: int, project_id: int, timeout: int, url: str
) -> None:
    """Dispatch and run an agent that performs a multi-step web workflow."""
    from app.core.context import thread_context_store
    from app.core.engine.background_agent import run_agent_background
    from app.core.engine.dispatch import dispatch_agent_run
    from app.core.engine.state.config import (
        AgentRuntimeConfig,
        ExecutionTicket,
        TicketParameters,
    )
    from app.infrastructure.config.service import SystemConfigService

    thread_context_store.set_working_directory(thread_id, os.getcwd())

    user_lang = SystemConfigService.get_language_preference()

    system_instructions = (
        "You are a web automation assistant. "
        f"Respond in {user_lang}. "
        "Your task is to interact with a local web form using the browser_control tool. "
        "Use ONLY these exact CSS selectors: input#username, input#email, button#submit, button#reset. "
        "Perform the following steps as separate browser_control tool calls, in order. "
        "Do not combine steps. "
        "1. Navigate to the URL using action='navigate'. "
        "2. Verify the page loaded by getting the text of the h1 heading (selector='h1'). "
        "3. Type 'alice' into input#username using action='type_text'. "
        "4. Type 'alice@example.com' into input#email using action='type_text'. "
        "5. Click button#submit using action='click'. "
        "6. Get the text from div#result using action='get_text'. "
        "7. Click button#reset using action='click'. "
        "8. Type 'bob' into input#username using action='type_text'. "
        "9. Type 'bob@example.com' into input#email using action='type_text'. "
        "10. Click button#submit using action='click'. "
        "11. Get the text from div#result using action='get_text'. "
        "After step 11, report the task is completed."
    )

    message = (
        f"Use browser_control to complete the web form at {url}. "
        "Follow the system instructions exactly, using the exact selectors provided. "
        "Each step must be a separate browser_control tool call. "
        "After collecting the two result texts, summarize them and stop."
    )

    logger.info("[Test] Dispatching agent run (thread_id=%s)...", thread_id)
    result = await dispatch_agent_run(
        thread_id=thread_id,
        message_content=message,
        project_id=project_id,
        skip_message_persistence=True,
    )
    if result.status == "failed":
        raise RuntimeError(f"Dispatch failed: {result.error}")

    ticket = ExecutionTicket(
        ticket_type="task",
        topic="web_automation",
        agent_config=AgentRuntimeConfig(
            role_name="Worker",
            system_instructions=system_instructions,
            tools=["browser_control"],
        ),
        parameters=TicketParameters(),
    )
    result.inputs["ticket"] = ticket.model_dump(mode="json")
    result.inputs["metadata"]["user_id"] = f"test-user-{member_id}"

    logger.info("[Test] Running agent (timeout=%ds)...", timeout)
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
    logger.info("[Test] Agent completed in %.1fs", elapsed)


async def _verify_results(thread_id: str) -> tuple[Macro, AgentActivity]:
    """Assert that the macro and activity records reflect a successful flywheel."""
    async with session_scope() as db:
        macro = (
            await db.execute(select(Macro).where(Macro.source_thread_id == thread_id))
        ).scalar_one_or_none()

    async with session_scope() as db:
        activity = await db.get(AgentActivity, thread_id)

    if activity is None:
        raise AssertionError(f"AgentActivity missing for thread {thread_id}")

    logger.info(
        "[Test] AgentActivity: final_outcome=%s eligible=%s summary=%s",
        activity.final_outcome,
        activity.macro_creation_eligible,
        activity.summary,
    )

    if activity.final_outcome.upper() != "COMPLETED":
        raise AssertionError(
            f"Expected COMPLETED, got {activity.final_outcome}. "
            f"Creation eligible={activity.macro_creation_eligible}."
        )
    if not activity.macro_creation_eligible:
        raise AssertionError(
            "Activity is not macro-creation-eligible. No replayable trace events found."
        )

    if macro is None:
        raise AssertionError(f"No macro was created for thread {thread_id}")

    assert macro.status == "pending_review", f"Unexpected macro status: {macro.status}"
    assert macro.is_active is False, "Macro should not be active yet"
    assert macro.source_thread_id == thread_id, (
        f"Wrong source_thread_id: {macro.source_thread_id}"
    )

    macro_script = MacroScript.from_yaml(macro.macro_script)
    step_count = len(macro_script.steps)
    action_steps = [
        s for s in macro_script.steps
        if s.type == MacroStepType.ACTION
    ]
    navigate_steps = [
        s for s in action_steps
        if s.event_type == MacroActionType.NAVIGATE
    ]
    type_steps = [
        s for s in action_steps
        if s.event_type in (MacroActionType.TYPE_TEXT, MacroActionType.INPUT)
    ]
    click_steps = [
        s for s in action_steps
        if s.event_type == MacroActionType.CLICK
    ]

    logger.info("[Test] Compiled macro step count: %d", step_count)
    logger.info("[Test] Action steps: %d", len(action_steps))
    logger.info(
        "[Test] Navigate: %d, Type/Input: %d, Click: %d",
        len(navigate_steps),
        len(type_steps),
        len(click_steps),
    )

    if step_count < MIN_STEPS:
        raise AssertionError(
            f"Expected macro with at least {MIN_STEPS} steps, got {step_count}."
        )
    if len(action_steps) < 6:
        raise AssertionError(
            f"Expected at least 6 action steps, got {len(action_steps)}."
        )
    if not navigate_steps:
        raise AssertionError("Macro is missing a navigate step.")
    if len(type_steps) < 2:
        raise AssertionError(
            f"Expected at least 2 type/input steps, got {len(type_steps)}."
        )
    if len(click_steps) < 2:
        raise AssertionError(
            f"Expected at least 2 click steps, got {len(click_steps)}."
        )

    logger.info(
        "[Test] Macro verified: id=%d name=%s step_count=%d status=%s member_id=%d",
        macro.id,
        macro.name,
        step_count,
        macro.status,
        macro.member_id,
    )
    return macro, activity


async def main() -> None:
    global MIN_STEPS

    parser = argparse.ArgumentParser(
        description="Macro Creation Web Workflow Manual Test with Real LLM"
    )
    parser.add_argument(
        "--timeout", type=int, default=TEST_TIMEOUT, help="Agent timeout in seconds"
    )
    parser.add_argument(
        "--min-steps", type=int, default=MIN_STEPS, help="Minimum expected macro steps"
    )
    args = parser.parse_args()
    MIN_STEPS = args.min_steps

    thread_id = f"macro-creation-web-workflow-{int(time.time())}"
    project_id = 1

    logger.info("=" * 60)
    logger.info("Macro Creation — Web Workflow Manual Test (Real LLM)")
    logger.info("=" * 60)
    logger.info("Thread ID: %s", thread_id)
    logger.info("Project ID: %d", project_id)
    logger.info("Timeout: %ds", args.timeout)
    logger.info("Minimum expected steps: %d", MIN_STEPS)
    logger.info("")

    temp_dir = tempfile.mkdtemp(prefix="web_macro_test_")
    form_path = os.path.join(temp_dir, "form.html")
    with open(form_path, "w", encoding="utf-8") as f:
        f.write(HTML_FORM)

    httpd = None
    try:
        await _init_backend()
        member_id = await _login_and_store_token()

        port = _find_free_port()
        httpd = _start_static_server(temp_dir, port)
        url = f"http://localhost:{port}/form.html"
        logger.info("[Test] Test form URL: %s", url)
        time.sleep(1)

        system_bus.clear()
        MacroSedimentationSubscriber()
        logger.info("[Test] Registered MacroSedimentationSubscriber")

        await _run_agent(thread_id, member_id, project_id, args.timeout, url)
        await _verify_results(thread_id)

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ MACRO CREATION WEB WORKFLOW TEST PASSED")
        logger.info("=" * 60)
        logger.info("Thread ID: %s", thread_id)

    except (AssertionError, RuntimeError) as e:
        logger.error("❌ TEST FAILED: %s", e)
        raise
    except Exception as e:
        logger.exception("❌ TEST FAILED: %s", e)
        raise
    finally:
        if httpd is not None:
            logger.info("[Test] Stopping static server...")
            httpd.shutdown()
        try:
            from app.infrastructure.drivers.browser import browser_manager

            await browser_manager.close()
            logger.info("[Test] Browser closed.")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            logger.warning("[Test] Closing browser failed: %s", e)
        try:
            os.remove(form_path)
            os.rmdir(temp_dir)
        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.warning("[Test] Cleanup temp dir failed: %s", e)
        logger.info("[Test] Cleaning up database resources...")
        await db_resource_manager.shutdown()
        logger.info("[Test] Cleanup complete.")


if __name__ == "__main__":
    asyncio.run(main())
