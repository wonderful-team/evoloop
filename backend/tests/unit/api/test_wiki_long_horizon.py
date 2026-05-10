"""
Tests for Wiki API Long-Horizon Flag

Verifies that the wiki generation endpoint correctly injects
metadata["long_horizon"] = True into the agent inputs.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import BackgroundTasks

from app.domain.wiki.schemas import WikiGenerationRequest


class TestWikiGenerationLongHorizon:
    """Tests for wiki generation API long-horizon injection."""

    @pytest.mark.asyncio
    async def test_generate_wiki_sets_long_horizon_flag(self):
        """The generate_wiki endpoint must set long_horizon=True in metadata."""
        from app.api.routes.wiki import generate_wiki

        req = WikiGenerationRequest(project_id=1, topic="Test", force_regenerate=False)

        # Mock all dependencies
        with patch("app.api.routes.wiki._resolve_project_path", return_value="/tmp/fake_project"), \
             patch("app.api.routes.wiki._ensure_wiki_generation_skill", new_callable=AsyncMock, return_value=MagicMock(id=42)), \
             patch("app.api.routes.wiki.SystemConfigService.get_language_preference", return_value="zh"), \
             patch("app.core.context.thread_context_store"), \
             patch("app.api.routes.wiki.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch, \
             patch("os.path.isdir", return_value=True):

            mock_result = MagicMock()
            mock_result.status = "queued"
            mock_result.inputs = {
                "messages": [],
            }
            mock_result.error = None
            mock_dispatch.return_value = mock_result

            bg_tasks = BackgroundTasks()
            token = MagicMock()

            await generate_wiki(req, bg_tasks, token)

            # Verify dispatch was called
            assert mock_dispatch.called

            # Verify the inputs got long_horizon set
            assert mock_result.inputs["metadata"]["long_horizon"] is True
            assert mock_result.inputs["metadata"]["skip_persistence"] is True

    @pytest.mark.asyncio
    async def test_generate_wiki_creates_metadata_if_missing(self):
        """If inputs has no metadata dict, one should be created."""
        from app.api.routes.wiki import generate_wiki

        req = WikiGenerationRequest(project_id=1, topic="Test")

        with patch("app.api.routes.wiki._resolve_project_path", return_value="/tmp/fake_project"), \
             patch("app.api.routes.wiki._ensure_wiki_generation_skill", new_callable=AsyncMock, return_value=MagicMock(id=42)), \
             patch("app.api.routes.wiki.SystemConfigService.get_language_preference", return_value="en"), \
             patch("app.core.context.thread_context_store"), \
             patch("app.api.routes.wiki.dispatch_agent_run", new_callable=AsyncMock) as mock_dispatch, \
             patch("os.path.isdir", return_value=True):

            mock_result = MagicMock()
            mock_result.status = "queued"
            mock_result.inputs = {}  # No metadata at all
            mock_result.error = None
            mock_dispatch.return_value = mock_result

            bg_tasks = BackgroundTasks()
            token = MagicMock()

            await generate_wiki(req, bg_tasks, token)

            assert "metadata" in mock_result.inputs
            assert mock_result.inputs["metadata"]["long_horizon"] is True
            assert mock_result.inputs["metadata"]["skip_persistence"] is True
