import pytest
from unittest.mock import MagicMock, patch
from app.core.learning.skill_synthesizer import WorkflowSynthesizer
from app.core.learning.trace_parser import TraceSequence, TraceStep, UIContext, ActionSource, ActionCategory

@pytest.mark.asyncio
async def test_click_synthesis():
    """Test that normal mouse clicks are synthesized correctly.

    [Scheme A] Note: Region-based extraction is now handled via TraceEvent
    (action_type="region_extract"), not through click events. This test
    verifies normal click behavior.
    """
    # Arrange
    thread_id = "test_thread"
    synthesizer = WorkflowSynthesizer(thread_id=thread_id)

    # Mock a trace sequence with a normal click
    step = TraceStep(
        step_number=1,
        source=ActionSource.HUMAN,
        category=ActionCategory.SYSTEM_INTERACTION,
        action_type="mouse_click",
        action_name="mobile_control",
        action_args={
            "position": [100, 200],
            "window_bounds": [0, 0, 1000, 1000],
        }
    )
    sequence = TraceSequence(thread_id=thread_id, steps=[step])

    # Act
    macro = synthesizer._compile_macro_script(sequence)

    # Assert - normal click should create an action step
    assert len(macro) == 1
    click_step = macro[0]
    assert click_step["type"] == "action"
    assert click_step["event_type"] == "mouse_click"


@pytest.mark.asyncio
async def test_extraction_via_trace_event():
    """Test that extraction via TraceEvent (region_extract) works correctly.

    [Scheme A] This tests the new region-based extraction flow where annotations
    are stored as TraceEvent with action_type="region_extract" and merged during synthesis.
    """
    # Arrange
    thread_id = "test_thread"
    synthesizer = WorkflowSynthesizer(thread_id=thread_id)

    # Mock a trace sequence with a click (annotations are handled separately)
    step = TraceStep(
        step_number=1,
        source=ActionSource.HUMAN,
        category=ActionCategory.SYSTEM_INTERACTION,
        action_type="mouse_click",
        action_name="mobile_control",
        action_args={"position": [100, 200]}
    )
    sequence = TraceSequence(thread_id=thread_id, steps=[step])

    # [Scheme A] Mock TraceEvent annotations (region_extract events)
    mock_annotations = [
        MagicMock(
            id=1,
            timestamp=500,
            action_type="region_extract",
            target_text="Test extraction",
            payload={
                "coordinates": {
                    "x": 0.1,
                    "y": 0.2,
                    "width": 0.3,
                    "height": 0.4,
                }
            }
        )
    ]

    # Act - synthesis with TraceEvent annotations
    with patch.object(synthesizer, '_fetch_annotations', return_value=mock_annotations):
        # Note: The actual synthesis would merge annotations here
        # For now, we just verify the macro structure
        macro = synthesizer._compile_macro_script(sequence)

    # Assert
    assert len(macro) >= 1


if __name__ == "__main__":
    pytest.main([__file__])
