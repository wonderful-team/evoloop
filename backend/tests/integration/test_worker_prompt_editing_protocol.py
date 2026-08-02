"""
Integration tests for Worker prompt editing protocol injection.

pytest tests/integration/test_worker_prompt_editing_protocol.py -v
"""

import pytest

from app.core.engine.nodes.prompts import WorkerPromptBuilder
from app.core.engine.state.config import AgentRuntimeConfig


class TestWorkerPromptEditingProtocol:
    """Validate that editing protocol is conditionally injected into Worker prompts."""

    @pytest.fixture
    def coding_worker_config(self):
        return AgentRuntimeConfig(
            role_name="coding_worker",
            system_instructions="You are a coding specialist.",
        )

    @pytest.fixture
    def android_worker_config(self):
        return AgentRuntimeConfig(
            role_name="android_worker",
            system_instructions="You are an Android debugging specialist.",
        )

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

    @pytest.mark.asyncio
    async def test_coding_worker_has_editing_protocol(self, coding_worker_config, sample_blackboard):
        builder = WorkerPromptBuilder(
            agent_config=coding_worker_config,
            blackboard=sample_blackboard,
            skills=[],
            ticket=sample_blackboard["ticket"]
        )
        prompt = await builder.build()
        if not isinstance(prompt, str):
            pytest.skip("Non-string prompt")

        assert "File Editing Protocol" in prompt, "coding_worker should have editing protocol"
        # After upgrade, should mention fuzzy matching and tool selection
        assert "cascading fuzzy matching" in prompt.lower(), "Should mention fuzzy matching"
        assert "edits" in prompt.lower(), "Should reference edits parameter"

    @pytest.mark.asyncio
    async def test_android_worker_has_editing_protocol(self, android_worker_config, sample_blackboard):
        """All workers now have editing protocol, not just coding_worker."""
        builder = WorkerPromptBuilder(
            agent_config=android_worker_config,
            blackboard=sample_blackboard,
            skills=[],
            ticket=sample_blackboard["ticket"]
        )
        prompt = await builder.build()
        if not isinstance(prompt, str):
            pytest.skip("Non-string prompt")

        assert "File Editing Protocol" in prompt, "android_worker should have editing protocol"

    def test_edit_file_description_reshaped(self, coding_worker_config, sample_blackboard):
        """Verify that edit_file tool description contains behavior-shaping language."""
        from app.domain.tools.files.edit_file import edit_file

        # Get the actual tool description (StructuredTool wraps the function)
        doc = edit_file.description if hasattr(edit_file, 'description') else (edit_file.__doc__ or "")
        assert "read_file" in doc.lower(), "Should instruct to read first"
        assert "cascading fuzzy matching" in doc.lower(), "Should mention fuzzy matching"

    def test_edit_file_description_has_multiedit_mode(self):
        """Verify edit_file description contains multi-edit guidance."""
        from app.domain.tools.files.edit_file import edit_file
        # Get the description from the StructuredTool
        if hasattr(edit_file, 'description'):
            doc = edit_file.description or ""
        else:
            doc = edit_file.__doc__ or ""
        
        # Check for key phrases
        assert "edits" in doc.lower(), "Should guide LLM to use edits parameter for multi-edit"
