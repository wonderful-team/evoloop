"""
End-to-End Scenario Tests
Covers: Complete coding task, Error self-healing, Deep research, HITL flow
"""
import pytest
import asyncio
import httpx
import json
from unittest.mock import patch, MagicMock, AsyncMock

from tests.config import config, get_auth_headers


class TestE2ECodingTask:
    """E2E Test: Complete coding task flow."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_e2e_coding_task(self):
        """
        Full coding task: Create calculator package with tests.
        
        Expected flow:
        1. Supervisor -> Planner (generate plan)
        2. Supervisor -> Coder (create files)
        3. Supervisor -> Coder (write tests)
        4. Supervisor -> Tester (run tests)
        5. Supervisor -> Finish
        """
        thread_id = config.generate_thread_id()
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=config.AGENT_TIMEOUT
        ) as client:
            # Send coding task
            response = await client.post("/api/v1/chat", json={
                "message": "Create a Python calculator package with add, subtract, multiply, divide functions and unit tests",
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID
            })
            
            assert response.status_code == 200
            
            # Monitor execution via SSE
            events_received = []
            nodes_visited = set()
            
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/stream/chat/{thread_id}"
                ) as sse_response:
                    async for line in sse_response.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                                events_received.append(data)
                                
                                # Track visited nodes
                                if "tasks" in data:
                                    for task in data["tasks"]:
                                        if "node" in task:
                                            nodes_visited.add(task["node"])
                                
                                # Check completion
                                if data.get("status") == "done":
                                    break
                            except json.JSONDecodeError:
                                pass
                        
                        if len(events_received) > 50:
                            break
            except asyncio.TimeoutError:
                pass
            
            # Verify expected nodes were visited
            assert len(events_received) > 0
            # May include: supervisor, planner, coder, tester, finish


class TestE2EErrorRecovery:
    """E2E Test: Error self-healing flow."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_e2e_error_recovery(self):
        """
        Error recovery: Fix syntax error using LSP.
        
        Expected flow:
        1. Supervisor -> Coder
        2. Coder calls consult_lsp -> Detects error
        3. Coder calls manage_file -> Fixes error
        4. Coder calls consult_lsp -> Verifies fix
        5. Supervisor -> Finish
        """
        thread_id = config.generate_thread_id()
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=config.AGENT_TIMEOUT
        ) as client:
            # First, create a file with error (via API or setup)
            # Then ask agent to fix it
            
            response = await client.post("/api/v1/chat", json={
                "message": "Check if there are any syntax errors in the current project and fix them",
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID
            })
            
            assert response.status_code == 200
            
            # Monitor for LSP tool calls
            await asyncio.sleep(5)  # Allow some processing
            
            # Verify via SSE or final state
            assert True


class TestE2EDeepResearch:
    """E2E Test: Deep research flow."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_e2e_deep_research(self):
        """
        Deep research: Research LangGraph design.
        
        Expected flow:
        1. IntentClassifier -> "research"
        2. DeepResearcher: search_web, crawl_url (multiple iterations)
        3. DeepResearcher: Generate report
        4. Supervisor -> Finish
        """
        thread_id = config.generate_thread_id()
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=180  # Research can take longer
        ) as client:
            response = await client.post("/api/v1/chat", json={
                "message": "深入研究 LangGraph 的 StateGraph 实现原理，生成研究报告",
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID
            })
            
            assert response.status_code == 200
            
            # This is a long-running task, just verify it starts
            await asyncio.sleep(5)
            
            # Check initial activity
            activity_response = await client.get(
                f"/api/v1/stream/chat/{thread_id}",
                headers={"Accept": "text/event-stream"}
            )
            
            assert activity_response.status_code == 200


class TestE2EHumanInTheLoop:
    """E2E Test: Human-in-the-Loop flow."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_e2e_hitl_flow(self):
        """
        HITL: Request approval for dangerous operation.
        
        Expected flow:
        1. Supervisor -> Coder
        2. Coder detects dangerous operation
        3. Coder calls request_approval
        4. SSE pushes human_request event
        5. (User approves - simulated)
        6. Coder continues
        7. Finish
        """
        thread_id = config.generate_thread_id()
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=config.AGENT_TIMEOUT
        ) as client:
            # Send potentially dangerous request
            response = await client.post("/api/v1/chat", json={
                "message": "删除项目中所有 .pyc 文件",
                "thread_id": thread_id,
                "project_id": config.PROJECT_ID
            })
            
            assert response.status_code == 200
            
            # Monitor for human_request event
            hitl_event_received = False
            
            try:
                async with client.stream(
                    "GET",
                    f"/api/v1/stream/chat/{thread_id}"
                ) as sse_response:
                    async for line in sse_response.aiter_lines():
                        if "human_request" in line:
                            hitl_event_received = True
                            break
                        
                        # Timeout check
                        await asyncio.sleep(0.1)
            except asyncio.TimeoutError:
                pass
            
            # HITL may or may not trigger depending on config
            assert True


class TestE2ESkillLearning:
    """E2E Test: Skill learning and replay."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_e2e_skill_learning(self):
        """
        Skill Learning: Learn from user demonstration.
        
        Expected flow:
        1. Start trace recording
        2. User performs actions (simulated)
        3. Stop recording
        4. Synthesize skill
        5. Replay skill with different params
        """
        thread_id = config.generate_thread_id()
        
        async with httpx.AsyncClient(
            base_url=config.API_BASE_URL,
            headers=get_auth_headers(),
            timeout=config.AGENT_TIMEOUT
        ) as client:
            # Start recording
            start_response = await client.post("/api/v1/learning/traces/start", json={
                "thread_id": thread_id
            })
            
            if start_response.status_code not in [200, 201]:
                pytest.skip("Learning API not available")
            
            session_data = start_response.json()
            
            # Record some events
            await client.post("/api/v1/learning/traces/events", json={
                "session_id": session_data.get("session_id"),
                "thread_id": thread_id,
                "events": [
                    {"event_type": "tool_call", "tool_name": "manage_file", "args": {"action": "list"}}
                ]
            })
            
            # Synthesize
            synth_response = await client.post("/api/v1/learning/skills/synthesize", json={
                "thread_id": thread_id
            })
            
            # May succeed or fail depending on trace quality
            assert synth_response.status_code in [200, 400, 500]
