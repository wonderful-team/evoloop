import asyncio
import uuid
import json
from datetime import datetime
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import TraceEvent, LearnedSkill
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.execution.macro_engine import MacroEngine
from unittest.mock import AsyncMock, patch

async def run_e2e_hybrid_test():
    """
    E2E Test: Simulation of User Recording -> Synthesis -> Deterministic Execution.
    """
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"
    session_id = f"sess-{uuid.uuid4().hex[:8]}"
    project_id = 1
    
    print(f"🚀 Starting E2E Hybrid Test (Thread: {thread_id}, Session: {session_id})")

    # 1. Simulate Recording (Insert Trace Events)
    async with session_scope() as db:
        events = [
            TraceEvent(
                thread_id=thread_id,
                session_id=session_id,
                recording_session_id=session_id,
                step_number=1,
                node_name="browser_interaction",
                action_type="tool_call",
                action_payload=json.dumps({
                    "name": "browser_control", 
                    "args": {"action": "navigate", "url": "https://www.example.com"}
                }),
                state_snapshot=json.dumps({"url": "about:blank"}),
                is_human_action=True,
                timestamp=datetime.now().timestamp()
            ),
            TraceEvent(
                thread_id=thread_id,
                session_id=session_id,
                recording_session_id=session_id,
                step_number=2,
                node_name="browser_interaction",
                action_type="click",
                target_selector="a.more-info",
                action_payload=json.dumps({"selector": "a.more-info"}),
                state_snapshot=json.dumps({"url": "https://www.example.com"}),
                is_human_action=True,
                timestamp=datetime.now().timestamp()
            )
        ]
        for e in events:
            db.add(e)
        await db.commit()
    print("✅ Step 1: Mock Trace Events recorded in DB.")

    # 2. Trigger Synthesis
    # Note: We mock the LLM part of synthesizer to avoid wasting tokens/time
    with patch("app.core.learning.skill_synthesizer.WorkflowSynthesizer._generate_skill_yaml") as mock_llm:
        mock_llm.return_value = """
name: ExampleClicker
description: Navigate and click more info
trigger_patterns: ["click example"]
parameters: []
preconditions: []
instructions: "Go to example.com and click more info"
"""
        synthesizer = WorkflowSynthesizer(thread_id, session_id)
        skill = await synthesizer.synthesize()
        
        print(f"✅ Step 2: Skill '{skill.name}' synthesized.")
        assert skill.execution_mode == "deterministic", "Should default to deterministic for pure browser trace"
        assert len(skill.macro_script) == 2, "Macro script should have 2 steps"
        print(f"   Macro Script: {json.dumps(skill.macro_script, indent=2)}")

    # Patch the internal execution methods to verify logic without Pydantic tool friction
    with patch("app.core.execution.macro_engine.MacroEngine._execute_browser_step", new_callable=AsyncMock) as mock_browser_step:
        with patch("app.core.execution.macro_engine.activity_monitor", new_callable=AsyncMock):
            # Simulate execution
            result = await MacroEngine.execute(thread_id, skill.macro_script)
            
            print("✅ Step 3: MacroEngine execution simulation.")
            assert result["success"] is True
            assert mock_browser_step.call_count == 2
            
            # Verify internal calls are correct
            mock_browser_step.assert_any_call("goto", None, {"action": "navigate", "url": "https://www.example.com"})
            mock_browser_step.assert_any_call("click", "a.more-info", {"selector": "a.more-info"})

    print("🎉 E2E Hybrid Execution Flow Verified Successfully!")

if __name__ == "__main__":
    asyncio.run(run_e2e_hybrid_test())
