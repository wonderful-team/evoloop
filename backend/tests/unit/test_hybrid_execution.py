import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch
from app.core.execution.macro_engine import MacroEngine
from app.api.routes.learning import execute_skill
from app.models.learning import LearnedSkill
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.learning.trace_parser import TraceSequence, TraceStep, ActionSource, ActionCategory

@pytest.mark.asyncio
async def test_macro_engine_browser_execution():
    """Verify MacroEngine correctly maps JSON steps to browser_control."""
    # Use a more forceful patch that doesn't trigger Pydantic validation on the StructuredTool object
    import app.core.execution.macro_engine
    with patch.object(app.core.execution.macro_engine.browser_control, "ainvoke", new_callable=AsyncMock) as mock_browser:
        macro_script = [
            {
                "step_number": 1,
                "event_type": "goto",
                "source": "dom",
                "payload": {"url": "https://example.com"}
            },
            {
                "step_number": 2,
                "event_type": "click",
                "source": "dom",
                "target_selector": "button#search"
            }
        ]
        
        # Mock activity_monitor and DB session
        with patch("app.core.execution.macro_engine.activity_monitor", new_callable=AsyncMock), \
             patch("app.core.execution.macro_engine.session_scope", new_callable=AsyncMock):
            result = await MacroEngine.execute("test_thread", macro_script)
            
            assert result["success"] is True
            assert mock_browser.call_count == 2
            mock_browser.assert_any_call({"action": "navigate", "url": "https://example.com"})
            mock_browser.assert_any_call({"action": "click", "selector": "button#search"})

@pytest.mark.asyncio
async def test_hybrid_routing_logic():
    """Verify execute_skill API correctly branches between agentic and deterministic."""
    mock_db = AsyncMock()
    mock_bg_tasks = AsyncMock()
    
    # 1. Test Deterministic Branch
    skill_deterministic = LearnedSkill(
        id=1,
        name="FastSkill",
        execution_mode="deterministic",
        macro_script=[{"event_type": "goto", "payload": {"url": "test.com"}}]
    )
    
    # Mock SQL session.get
    mock_db.get.return_value = skill_deterministic
    
    # We need to mock internal imports and functions inside execute_skill
    with patch("app.api.routes.learning.session_scope") as mock_scope:
        mock_scope.return_value.__aenter__.return_value = mock_db
        with patch("app.api.routes.learning.run_agent_background") as mock_agent_task:
            with patch("app.core.execution.macro_engine.MacroEngine.execute") as mock_macro_task:
                from app.api.routes.learning import ExecuteSkillRequest
                body = ExecuteSkillRequest(thread_id="t1", project_id=1, params={})
                
                await execute_skill(skill_id=1, body=body, bg_tasks=mock_bg_tasks)
                
                # Check if MacroEngine was queued
                mock_bg_tasks.add_task.assert_called_once()
                # Verify it wasn't the agent task
                assert mock_agent_task.call_count == 0

@pytest.mark.asyncio
async def test_synthesizer_macro_compilation():
    """Verify WorkflowSynthesizer correctly extracts macro steps from a TraceSequence."""
    synth = WorkflowSynthesizer("thread_1")
    
    # Create a mock sequence
    seq = TraceSequence(thread_id="thread_1")
    seq.steps = [
        TraceStep(
            step_number=1,
            source=ActionSource.AGENT,
            category=ActionCategory.QUERY,
            action_type="tool_call",
            action_name="browser_control",
            action_args={"action": "navigate", "url": "https://goofish.com"},
            node_name="browser_node"
        ),
        TraceStep(
            step_number=2,
            source=ActionSource.AGENT,
            category=ActionCategory.INTERACTION,
            action_type="click",
            action_name="click",
            action_args={"selector": "button.search"},
            ui_context=AsyncMock(element_selector="button.search"),
            node_name="browser_node"
        )
    ]
    
    macro = synth._compile_macro_script(seq)
    
    assert len(macro) == 2
    assert macro[0]["event_type"] == "goto"
    assert macro[1]["event_type"] == "click"
    assert macro[1]["target_selector"] == "button.search"

if __name__ == "__main__":
    asyncio.run(test_macro_engine_browser_execution())
    print("✅ MacroEngine logic verified!")
