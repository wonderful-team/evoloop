import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.learning.trace_parser import TraceSequence, TraceStep, ActionSource, ActionCategory

@pytest.mark.asyncio
async def test_full_pipeline_verification():
    thread_id = "full_pipeline_test"
    synthesizer = WorkflowSynthesizer(thread_id=thread_id)
    
    # 1. Mock TraceSequence
    step = TraceStep(
        step_number=1,
        source=ActionSource.HUMAN,
        category=ActionCategory.SYSTEM_INTERACTION,
        action_type="mouse_click",
        action_name="mobile_control",
        action_args={"position": [100, 200], "window_bounds": [0, 0, 1000, 1000]}
    )
    sequence = TraceSequence(thread_id=thread_id, steps=[step])
    
    # 2. Mock MacroService.run (Verification stage)
    # 3. Mock LLMFactory.create_llm (Synthesis stage)
    with patch("app.core.execution.macro.service.MacroService.run", new_callable=AsyncMock) as mock_run, \
         patch("app.infrastructure.llm.factory.LLMFactory.create_llm") as mock_llm_factory:
        
        # Successful verification
        mock_run.return_value = {"success": True, "extracted_data": {"extracted_1": "some_data"}}
        
        # Successful synthesis
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(content="""
```yaml
name: test_skill
description: verified skill
namespace: test
trigger_patterns: ["test"]
parameters: []
instructions: "# Expert Guide"
macro_script:
  - step_number: 1
    type: while
    description: loop
    condition: {type: element_exists, target_selector: ".next"}
    do: []
```
""")
        mock_llm_factory.return_value = mock_llm
        
        # Act
        with patch.object(synthesizer.parser, "to_narrative", return_value="narrative"), \
             patch.object(synthesizer.parser, "parse", new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = sequence
            skill = await synthesizer.synthesize()
        
        # Assert
        assert skill is not None
        assert skill.name == "test_skill"
        assert skill.macro_script[0]["type"] == "while"  # Prefers LLM loop over linear step
        assert mock_run.called
        assert mock_llm.ainvoke.called

if __name__ == "__main__":
    asyncio.run(test_full_pipeline_verification())
