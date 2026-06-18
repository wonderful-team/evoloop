"""
Skill Sync Service — Bidirectional Sync Coordination

Coordinates synchronization between the skills filesystem (~/.evoloop/skills/)
and the LearnedSkill database table, preventing infinite sync loops.
"""

import logging
import os
import shutil
import threading

from app.core.config import settings
from app.core.learning.skill_importer import SkillImporter
from app.core.learning.synthesizer_utils import export_skill_to_filesystem
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


class SkillSyncService:
    """
    Coordinates bidirectional sync between skills filesystem and DB.
    Uses a reentrant lock to prevent File→DB→File loop cycles.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sync_in_progress = False

    def acquire_sync_lock(self) -> bool:
        """
        Attempt to acquire the sync lock.
        Returns True if caller should proceed, False if a sync is already in progress.
        """
        if self._sync_in_progress:
            return False
        self._lock.acquire()
        try:
            if self._sync_in_progress:
                return False
            self._sync_in_progress = True
            return True
        finally:
            self._lock.release()

    def release_sync_lock(self):
        with self._lock:
            self._sync_in_progress = False

    async def export_skill_to_file(self, skill_id: int) -> str | None:
        """
        DB → File: Read a skill from DB and write its SKILL.md to disk.
        """
        if not self.acquire_sync_lock():
            logger.debug(f"[Sync] Skipping DB→File export for skill {skill_id}: sync lock held")
            return None

        try:
            async with session_scope() as db:
                from sqlalchemy import select
                stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
                skill = (await db.execute(stmt)).scalar_one_or_none()

            if not skill:
                logger.warning(f"[Sync] Skill {skill_id} not found for file export")
                return None

            # Use the existing export function
            path = export_skill_to_filesystem(skill)

            if path:
                # Ensure resource_path is set on the skill
                skill_dir = os.path.dirname(path)
                async with session_scope() as db:
                    stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
                    db_skill = (await db.execute(stmt)).scalar_one_or_none()
                    if db_skill and not db_skill.resource_path:
                        db_skill.resource_path = skill_dir

            return path
        except Exception as e:
            logger.error(f"[Sync] Failed to export skill {skill_id} to file: {e}")
            return None
        finally:
            self.release_sync_lock()

    async def delete_skill_file(self, skill_id: int, namespace: str | None = None, name: str | None = None) -> bool:
        """
        DB → File: Delete a skill's physical directory from disk.

        Args:
            skill_id: The skill ID (used as fallback to look up name/namespace)
            namespace: The skill namespace (if known, saves a DB query)
            name: The skill name (if known, saves a DB query)
        """
        if not self.acquire_sync_lock():
            logger.debug(f"[Sync] Skipping file deletion for skill {skill_id}: sync lock held")
            return False

        try:
            actual_namespace = namespace
            actual_name = name

            if not actual_namespace or not actual_name:
                async with session_scope() as db:
                    from sqlalchemy import select
                    stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
                    skill = (await db.execute(stmt)).scalar_one_or_none()
                    if skill:
                        actual_namespace = skill.namespace or "misc"
                        actual_name = skill.name

            if actual_namespace and actual_name:
                skill_dir = os.path.join(settings.SKILLS_DIR, actual_namespace, actual_name)
                if os.path.isdir(skill_dir):
                    shutil.rmtree(skill_dir)
                    logger.info(f"[Sync] Deleted skill directory: {skill_dir}")
                    return True

            # Also try resource_path
            if not actual_namespace and not actual_name:
                async with session_scope() as db:
                    from sqlalchemy import select
                    stmt = select(LearnedSkill).where(LearnedSkill.id == skill_id)
                    skill = (await db.execute(stmt)).scalar_one_or_none()
                    if skill and skill.resource_path:
                        path = skill.resource_path
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                            logger.info(f"[Sync] Deleted skill directory by resource_path: {path}")
                            return True

            return False
        except Exception as e:
            logger.error(f"[Sync] Failed to delete skill file for {skill_id}: {e}")
            return False
        finally:
            self.release_sync_lock()

    async def import_skill_from_disk(self, skill_md_path: str) -> bool:
        """
        File → DB: Import or update a skill from a SKILL.md file.

        Args:
            skill_md_path: Absolute path to a SKILL.md file
        """
        if not self.acquire_sync_lock():
            logger.debug(f"[Sync] Skipping File→DB import for {skill_md_path}: sync lock held")
            return False

        try:
            folder = os.path.dirname(skill_md_path)
            root_dir = settings.SKILLS_DIR

            # Calculate namespace relative to SKILLS_DIR
            try:
                namespace = str(os.path.relpath(os.path.dirname(folder), root_dir))
                if namespace == ".":
                    namespace = "misc"
            except ValueError:
                namespace = "misc"

            from pathlib import Path
            success = await SkillImporter.import_single_skill(Path(folder), namespace=namespace)

            if success:
                from app.core.learning.discovery import skill_discovery
                await skill_discovery.reload()

            return success
        except Exception as e:
            logger.error(f"[Sync] Failed to import skill from {skill_md_path}: {e}")
            return False
        finally:
            self.release_sync_lock()

    async def delete_skill_by_path(self, skill_md_path: str) -> bool:
        """
        File → DB: Delete a skill from DB when its SKILL.md is removed from disk.

        Attempts to extract skill name from the SKILL.md file path.
        Falls back to inferring the skill name from the parent directory name.
        """
        if not self.acquire_sync_lock():
            logger.debug(f"[Sync] Skipping File→DB delete for {skill_md_path}: sync lock held")
            return False

        try:
            folder = os.path.dirname(skill_md_path)
            root_dir = settings.SKILLS_DIR

            # Infer namespace and name from directory structure
            try:
                rel = os.path.relpath(folder, root_dir)
                parts = rel.split(os.sep)
                if len(parts) >= 2:
                    inferred_namespace = os.sep.join(parts[:-1])
                    inferred_name = parts[-1]
                elif len(parts) == 1:
                    inferred_namespace = "misc"
                    inferred_name = parts[0]
                else:
                    inferred_namespace = "misc"
                    inferred_name = os.path.basename(folder)
            except ValueError:
                inferred_namespace = "misc"
                inferred_name = os.path.basename(folder)

            async with session_scope() as db:
                from sqlalchemy import select
                stmt = select(LearnedSkill).where(
                    LearnedSkill.name == inferred_name,
                    LearnedSkill.namespace == inferred_namespace,
                )
                skill = (await db.execute(stmt)).scalar_one_or_none()

                if skill:
                    await db.delete(skill)
                    logger.info(f"[Sync] Deleted skill from DB: {inferred_name} ({inferred_namespace})")
                    return True
                else:
                    logger.warning(f"[Sync] No DB skill found for deleted file: {inferred_name} ({inferred_namespace})")
                    return False

            from app.core.learning.discovery import skill_discovery
            await skill_discovery.reload()
        except Exception as e:
            logger.error(f"[Sync] Failed to delete skill by path {skill_md_path}: {e}")
            return False
        finally:
            self.release_sync_lock()


skill_sync_service = SkillSyncService()
