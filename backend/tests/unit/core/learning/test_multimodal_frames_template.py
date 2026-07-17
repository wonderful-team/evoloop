"""Regression test for the multimodal frames prompt template guards."""

from app.utils.template import render_template


def test_frames_template_renders_events_without_position():
    """Keyboard/back events have no position; the template must guard
    `evt.position` instead of indexing into None."""
    frames = [
        {
            "timestamp": 1.23456,
            "description": "home screen",
            "norm_events": [
                {"action": "click", "position": [0.5, 0.25], "position_desc": "center", "target_text": "OK"},
                {"action": "back_key", "position": None, "position_desc": "", "target_text": None},
            ],
        },
        {
            "timestamp": 2.5,
            "description": "list page",
            "norm_events": [],
        },
    ]

    text = render_template("core/vision/multimodal_frames.prompt.j2", frames=frames)

    assert "click at (0.5, 0.25)" in text
    assert 'Target: "OK"' in text
    assert "- back_key" in text
    assert "list page" in text
