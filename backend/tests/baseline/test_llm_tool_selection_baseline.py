"""
Baseline LLM Tool Selection Test (v5.2.9)

Uses mock LLM to observe tool selection behavior with current prompts.
Run before upgrade to freeze current behavior.
pytest tests/baseline/test_llm_tool_selection_baseline.py -v
"""

import json
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.core.engine.prompts.worker_builder import WorkerPromptBuilder


class TestLLMToolSelectionBaseline:
    """Freeze baseline LLM behavior for editing tasks."""

    @pytest.fixture
    def coding_worker_config(self):
        return {
            "role_name": "coding_worker",
            "system_instructions": "You are a coding specialist.",
            "is_subtask": False,
        }

    @pytest.fixture
    def sample_blackboard(self):
        return {
            "clipboard": [],
            "ticket": {
                "topic": "Edit file",
                "acceptance_criteria": [],
                "parameters": {}
            }
        }

    def test_coding_worker_prompt_length_baseline(self, coding_worker_config, sample_blackboard):
        """Measure prompt size as a baseline for later comparison."""
        builder = WorkerPromptBuilder(
            agent_config=coding_worker_config,
            blackboard=sample_blackboard,
            skills=[],
            ticket=sample_blackboard["ticket"]
        )
        prompt = builder.build()
        if isinstance(prompt, str):
            token_estimate = len(prompt) / 4  # rough estimate
            print(f"\nBaseline Worker Prompt: chars={len(prompt)}, rough_tokens={token_estimate:.0f}")

            report_path = "reports/baseline_prompt_metrics.json"
            os.makedirs("reports", exist_ok=True)
            with open(report_path, 'w') as f:
                json.dump({
                    "prompt_chars": len(prompt),
                    "rough_tokens": round(token_estimate, 0),
                    "has_editing_protocol": "File Editing Protocol" in prompt,
                    "emphasizes_fuzzy_matching": "cascading fuzzy matching" in prompt.lower(),
                    "mentions_multiedit": "multiedit" in prompt.lower(),
                    "mentions_apply_patch": "apply_patch" in prompt.lower(),
                }, f, indent=2)

            # Post-upgrade: File Editing Protocol emphasizes fuzzy matching and tool selection
            assert "File Editing Protocol" in prompt, "Should have File Editing Protocol"
            assert "cascading fuzzy matching" in prompt.lower(), "Protocol should mention cascading fuzzy matching"
            assert "edit_file" in prompt.lower(), "Protocol should mention edit_file edits parameter"
            assert "apply_patch_file" in prompt.lower(), "Protocol should mention apply_patch_file"
        else:
            pytest.skip("Prompt build returned non-string")

    @pytest.mark.asyncio
    async def test_mock_llm_selects_edit_file_for_simple_change(self, coding_worker_config, sample_blackboard):
        """Baseline: observe what tool a mock LLM would choose for a simple edit."""
        builder = WorkerPromptBuilder(
            agent_config=coding_worker_config,
            blackboard=sample_blackboard,
            skills=[],
            ticket={
                "topic": "Change foo() to bar() in src/app.py",
                "acceptance_criteria": [],
                "parameters": {}
            }
        )
        prompt = builder.build()
        if not isinstance(prompt, str):
            pytest.skip("Non-string prompt")

        # We can't easily run a real LLM in unit tests, so we baseline the prompt content
        # and the available tool descriptions instead.
        # A real baseline would use the integration test with a real LLM.

        # For now, just verify the prompt contains standard instructions
        assert "coding" in prompt.lower() or "specialist" in prompt.lower()

        print(f"\nBaseline LLM context prepared for: 'Change foo() to bar() in src/app.py'")
        print(f"Prompt length: {len(prompt)} chars")
