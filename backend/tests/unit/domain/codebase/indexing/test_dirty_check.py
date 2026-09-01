"""Regression tests for dirty_check timezone handling."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.codebase.indexing.dirty_check import is_file_changed_since_last_index


@pytest.mark.unit
async def test_naive_last_indexed_at_older_than_mtime_signals_changed(tmp_path):
    """SQLite returns last_indexed_at as offset-naive; comparison must still work."""
    repo_id = 2
    root = tmp_path / "repo"
    root.mkdir()
    file_path = root / "macro.yaml"
    file_path.write_text("hello", encoding="utf-8")

    session = AsyncMock()
    source_file = MagicMock()
    # Naive UTC datetime older than the file's mtime → file should be considered changed
    source_file.last_indexed_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    source_file.checksum = "old_checksum"

    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = source_file
    session.execute.return_value = result_mock

    with patch(
        "app.domain.codebase.indexing.dirty_check._resolve_repo_path",
        return_value=str(root),
    ):
        result = await is_file_changed_since_last_index(str(file_path), repo_id, session)

    assert result is True


@pytest.mark.unit
async def test_naive_last_indexed_at_newer_than_mtime_signals_unchanged(tmp_path):
    """A naive future last_indexed_at should suppress re-indexing via mtime."""
    repo_id = 2
    root = tmp_path / "repo"
    root.mkdir()
    file_path = root / "macro.yaml"
    file_path.write_text("hello", encoding="utf-8")

    session = AsyncMock()
    source_file = MagicMock()
    # Naive UTC datetime newer than the file's mtime → file should be skipped
    source_file.last_indexed_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    source_file.checksum = "old_checksum"

    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = source_file
    session.execute.return_value = result_mock

    with patch(
        "app.domain.codebase.indexing.dirty_check._resolve_repo_path",
        return_value=str(root),
    ):
        result = await is_file_changed_since_last_index(str(file_path), repo_id, session)

    assert result is False
