"""Unit tests for app.domain.codebase.indexing.dirty_check (P0.3a/§7)."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.indexing.dirty_check import is_file_changed_since_last_index


@pytest.fixture
def temp_file():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
        f.write("original content")
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


class TestIsFileChangedSinceLastIndex:
    async def _run(self, file_path, repo_id, sf_record, force=False):
        """Helper: mock _resolve_repo_path and run the function."""
        session = AsyncMock()
        mock_execute = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sf_record
        mock_execute.scalars = MagicMock(return_value=mock_scalars)
        session.execute = AsyncMock(return_value=mock_execute)

        with patch("app.domain.codebase.indexing.dirty_check._resolve_repo_path", return_value="/fake/repo"):
            return await is_file_changed_since_last_index(
                file_path, repo_id=repo_id, session=session, force=force,
            )

    async def test_new_file_is_changed(self, temp_file):
        """No SourceFile record => file is considered changed."""
        changed = await self._run(str(temp_file), repo_id=1, sf_record=None)
        assert changed is True

    async def test_same_content_not_changed(self, temp_file):
        """When checksum matches, file is NOT changed."""
        from app.core.file.hash import compute_md5
        content_hash = compute_md5("original content")
        mock_sf = MagicMock()
        mock_sf.checksum = content_hash

        changed = await self._run(str(temp_file), repo_id=1, sf_record=mock_sf)
        assert changed is False

    async def test_different_content_is_changed(self, temp_file):
        """When checksum differs, file IS changed."""
        mock_sf = MagicMock()
        mock_sf.checksum = "different_hash_value"

        changed = await self._run(str(temp_file), repo_id=1, sf_record=mock_sf)
        assert changed is True

    async def test_force_is_changed(self, temp_file):
        """force=True => always changed regardless of SourceFile record."""
        mock_sf = MagicMock()
        mock_sf.checksum = "anything"
        changed = await self._run(str(temp_file), repo_id=1, sf_record=mock_sf, force=True)
        assert changed is True

    async def test_nonexistent_file_is_changed(self):
        """Non-existent file returns True."""
        changed = await self._run("/nonexistent/file.py", repo_id=1, sf_record=None)
        assert changed is True
