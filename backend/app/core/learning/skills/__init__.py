"""Skill domain — discovery, lifecycle, import/sync, validation and visibility.

Consolidated from the flat ``core/learning`` skill_* modules so the skill
registry owns a single cohesive submodule. Public singletons are re-exported
here for convenience; prefer importing from the concrete module path
(``app.core.learning.skills.discovery`` etc.) where the symbol is defined.
"""

from app.core.learning.skills.discovery import SkillDiscovery, skill_discovery
from app.core.learning.skills.importer import SkillImporter
from app.core.learning.skills.lifecycle import (
    apply_validation_result,
    confirm_skill,
    create_from_synthesis,
    deduplicate_name,
    delete_skill,
    patch_skill,
    update_skill,
)
from app.core.learning.skills.repository import SkillRepository, skill_repository
from app.core.learning.skills.sync_service import SkillSyncService, skill_sync_service
from app.core.learning.skills.validator import SkillValidator
from app.core.learning.skills.visibility import is_routable, is_visible, visible_filter
from app.core.learning.skills.watcher import SkillsFileWatcher

__all__ = [
    "SkillDiscovery",
    "skill_discovery",
    "SkillImporter",
    "apply_validation_result",
    "confirm_skill",
    "create_from_synthesis",
    "deduplicate_name",
    "delete_skill",
    "patch_skill",
    "update_skill",
    "SkillRepository",
    "skill_repository",
    "SkillSyncService",
    "skill_sync_service",
    "SkillValidator",
    "is_routable",
    "is_visible",
    "visible_filter",
    "SkillsFileWatcher",
]
