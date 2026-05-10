"""
Tests for Worker Prompt Long-Horizon Guidance

Verifies that the worker.prompt.j2 template contains instructions
to prevent early stopping on long-horizon tasks.
"""

import pytest
import os


class TestWorkerPromptLongHorizon:
    """Tests for worker prompt template content."""

    @pytest.fixture
    def prompt_path(self):
        return os.path.join(
            os.path.dirname(__file__),
            "../../../../app/config/templates/core/engine/worker.prompt.j2",
        )

    def test_prompt_exists(self, prompt_path):
        assert os.path.isfile(prompt_path), f"Worker prompt not found at {prompt_path}"

    def test_contains_long_horizon_rule(self, prompt_path):
        with open(prompt_path) as f:
            content = f.read()
        assert "Long-Horizon Task Rule" in content, "Missing long-horizon task rule"

    def test_discourages_immediate_stop_with_remaining_steps(self, prompt_path):
        with open(prompt_path) as f:
            content = f.read()
        # Should mention continuing when more steps remain
        assert "continue executing until ALL steps are complete" in content
        assert "Do NOT stop after finishing only one page" in content

    def test_contains_continue_next_step_instruction(self, prompt_path):
        with open(prompt_path) as f:
            content = f.read()
        assert "If more steps remain" in content
        assert "Continue to the next step immediately" in content
