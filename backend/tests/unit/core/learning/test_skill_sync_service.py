"""
Functional tests for SkillSyncService — bidirectional sync between
filesystem (~/.evoloop/skills/) and LearnedSkill DB table.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.learning.skill_sync_service import SkillSyncService, skill_sync_service


@pytest.fixture(autouse=True)
def reset_sync_lock():
    """Reset the singleton's sync lock before each test."""
    skill_sync_service._sync_in_progress = False
    yield


@pytest.fixture
def mock_learned_skill():
    """Create a mock LearnedSkill instance."""
    skill = MagicMock()
    skill.id = 42
    skill.name = "test_skill"
    skill.namespace = "roles"
    skill.description = "A test skill"
    skill.trigger_patterns = ["test {param}"]
    skill.parameters = [{"name": "param", "type": "string"}]
    skill.preconditions = []
    skill.instructions = "# Test Skill\n\nDo something."
    skill.macro_script = None
    skill.resource_path = None
    return skill


@pytest.fixture
def mock_session(mock_learned_skill):
    """Mock an async DB session returning the mock skill."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_learned_skill
    session.execute.return_value = result
    return session


@pytest.fixture
def mock_session_none():
    """Mock an async DB session returning no skill."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    return session


@pytest.fixture
def patch_session_scope():
    """Factory fixture — patches session_scope in the service module."""
    def _patch(session):
        @asynccontextmanager
        async def _scope():
            yield session
        return patch("app.core.learning.skill_sync_service.session_scope", _scope)
    return _patch


# =============================================================================
# DB → File: export_skill_to_file
# =============================================================================

class TestExportSkillToFile:

    @pytest.mark.asyncio
    async def test_export_creates_skill_md_and_sets_resource_path(
        self, patch_session_scope, mock_session, mock_learned_skill, tmp_path,
    ):
        """Skill found in DB → export_skill_to_filesystem called → resource_path updated."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session):
                with patch(
                    "app.core.learning.skill_sync_service.export_skill_to_filesystem",
                    return_value=str(skills_dir / "roles" / "test_skill" / "SKILL.md"),
                ) as mock_export:
                    service = SkillSyncService()
                    result = await service.export_skill_to_file(42)

                    assert result is not None
                    assert "SKILL.md" in result
                    mock_export.assert_called_once_with(mock_learned_skill)

    @pytest.mark.asyncio
    async def test_export_skill_not_found_returns_none(
        self, patch_session_scope, mock_session_none,
    ):
        """Skill not in DB → returns None without calling export."""
        with patch_session_scope(mock_session_none):
            with patch(
                "app.core.learning.skill_sync_service.export_skill_to_filesystem"
            ) as mock_export:
                service = SkillSyncService()
                result = await service.export_skill_to_file(999)

                assert result is None
                mock_export.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_skipped_when_lock_held(self):
        """Sync lock already held → skip, return None."""
        skill_sync_service._sync_in_progress = True
        result = await skill_sync_service.export_skill_to_file(42)
        assert result is None

    @pytest.mark.asyncio
    async def test_export_releases_lock_on_exception(
        self, patch_session_scope, mock_session,
    ):
        """Exception during export → lock released, no hang."""
        with patch_session_scope(mock_session):
            with patch(
                "app.core.learning.skill_sync_service.export_skill_to_filesystem",
                side_effect=RuntimeError("disk full"),
            ):
                service = SkillSyncService()
                result = await service.export_skill_to_file(42)

                assert result is None
                assert service._sync_in_progress is False


# =============================================================================
# DB → File: delete_skill_file
# =============================================================================

class TestDeleteSkillFile:

    @pytest.mark.asyncio
    async def test_delete_by_namespace_and_name(
        self, patch_session_scope, mock_session, tmp_path,
    ):
        """Known namespace+name → deletes the directory from disk."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "roles" / "test_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("test")

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session):
                service = SkillSyncService()
                result = await service.delete_skill_file(
                    42, namespace="roles", name="test_skill"
                )

                assert result is True
                assert not skill_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_fallback_to_db_query(
        self, patch_session_scope, mock_session, mock_learned_skill, tmp_path,
    ):
        """No namespace/name passed → falls back to DB query."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "roles" / "test_skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("test")

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session):
                service = SkillSyncService()
                result = await service.delete_skill_file(42)

                assert result is True
                assert not skill_dir.exists()

    @pytest.mark.asyncio
    async def test_delete_skipped_when_lock_held(self):
        """Sync lock held → skip."""
        skill_sync_service._sync_in_progress = True
        result = await skill_sync_service.delete_skill_file(42)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_dir_returns_false(
        self, patch_session_scope, mock_session, mock_learned_skill, tmp_path,
    ):
        """Directory does not exist → returns False."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session):
                service = SkillSyncService()
                result = await service.delete_skill_file(42)

                assert result is False


# =============================================================================
# File → DB: import_skill_from_disk
# =============================================================================

class TestImportSkillFromDisk:

    @pytest.mark.asyncio
    async def test_import_existing_skill_md(
        self, patch_session_scope, mock_session, tmp_path,
    ):
        """Valid SKILL.md → calls SkillImporter.import_single_skill and reloads."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "roles" / "my_skill"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: my_skill\n---\n\nInstructions here.")

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session):
                with patch(
                    "app.core.learning.skill_sync_service.SkillImporter.import_single_skill",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as mock_importer:
                    with patch(
                        "app.core.learning.discovery.skill_discovery.reload",
                        new_callable=AsyncMock,
                    ) as mock_reload:
                        service = SkillSyncService()
                        result = await service.import_skill_from_disk(str(skill_md))

                        assert result is True
                        mock_importer.assert_called_once()
                        call_folder, call_kwargs = mock_importer.call_args
                        assert str(call_kwargs.get("namespace", call_folder[-1])) == "roles"
                        mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_nonexistent_file(self, tmp_path):
        """SKILL.md does not exist → returns False."""
        service = SkillSyncService()
        result = await service.import_skill_from_disk(
            str(tmp_path / "nonexistent" / "SKILL.md")
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_import_skipped_when_lock_held(self):
        """Sync lock held → skip."""
        skill_sync_service._sync_in_progress = True
        result = await skill_sync_service.import_skill_from_disk("/some/path")
        assert result is False


# =============================================================================
# File → DB: delete_skill_by_path
# =============================================================================

class TestDeleteSkillByPath:

    @pytest.mark.asyncio
    async def test_delete_matching_skill(
        self, patch_session_scope, mock_session, mock_learned_skill, tmp_path,
    ):
        """Skill found by inferred path → deletes from DB, then refreshes the
        discovery cache and publishes the delete event (convergence fix: the
        reload used to be dead code after an early return)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        mock_learned_skill.name = "my_skill"
        mock_learned_skill.namespace = "roles"

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session), patch(
                "app.core.learning.discovery.skill_discovery.reload", new=AsyncMock()
            ) as mock_reload, patch(
                "app.core.events.publishers.publish_skill_mutated", new=AsyncMock()
            ) as mock_publish:
                service = SkillSyncService()
                result = await service.delete_skill_by_path(
                    str(skills_dir / "roles" / "my_skill" / "SKILL.md")
                )

                assert result is True
                mock_session.delete.assert_called_once_with(mock_learned_skill)
                mock_reload.assert_awaited_once()
                mock_publish.assert_awaited_once()
                assert mock_publish.await_args.kwargs["action"] == "delete"

    @pytest.mark.asyncio
    async def test_delete_no_matching_skill(
        self, patch_session_scope, mock_session_none, tmp_path,
    ):
        """No skill matches inferred path → returns False, no delete."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        with patch("app.core.learning.skill_sync_service.settings") as mock_settings:
            mock_settings.SKILLS_DIR = str(skills_dir)
            with patch_session_scope(mock_session_none):
                service = SkillSyncService()
                result = await service.delete_skill_by_path(
                    str(skills_dir / "unknown" / "ghost" / "SKILL.md")
                )

                assert result is False

    @pytest.mark.asyncio
    async def test_delete_skipped_when_lock_held(self):
        """Sync lock held → skip."""
        skill_sync_service._sync_in_progress = True
        result = await skill_sync_service.delete_skill_by_path("/some/path")
        assert result is False


# =============================================================================
# Sync lock: reentrant guard
# =============================================================================

class TestSyncLock:

    def test_acquire_and_release(self):
        """Lock can be acquired and released."""
        service = SkillSyncService()
        assert service.acquire_sync_lock() is True
        assert service._sync_in_progress is True
        service.release_sync_lock()
        assert service._sync_in_progress is False

    def test_acquire_when_already_held(self):
        """Lock not reentrant — second acquire returns False."""
        service = SkillSyncService()
        service.acquire_sync_lock()
        assert service.acquire_sync_lock() is False
        service.release_sync_lock()

    def test_release_without_acquire_does_not_crash(self):
        """release_sync_lock when not held does not raise."""
        service = SkillSyncService()
        service.release_sync_lock()  # should not crash
