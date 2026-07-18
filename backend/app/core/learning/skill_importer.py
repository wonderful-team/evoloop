import logging
from pathlib import Path

from sqlalchemy import select

from app.core.learning.schemas import SkillImportResult
from app.core.learning.skill_validator import SkillValidator
from app.infrastructure.database import session_scope
from app.models.learning import LearnedSkill

logger = logging.getLogger(__name__)


def _extract_tools_required(metadata: dict) -> list[str]:
    """Extract required tool names from SKILL.md frontmatter.

    Supports the canonical layout:
        requires:
          tools: [tool_a, tool_b]

    Returns an empty list when the field is missing or malformed.
    """
    requires = metadata.get("requires") or {}
    if not isinstance(requires, dict):
        return []
    tools = requires.get("tools") or []
    if isinstance(tools, str):
        return [tools]
    if isinstance(tools, list):
        return [str(t) for t in tools if t]
    return []


class SkillImporter:
    """
    Service to import external skill packages (SKILL.md) into the Evoloop database.
    """

    @staticmethod
    async def import_from_directory(root_dir: str) -> SkillImportResult:
        """
        Scan a directory recursively for skill folders and import them.
        Each folder must contain a SKILL.md file.
        """
        results = SkillImportResult()

        root_path = Path(root_dir)
        if not root_path.exists():
            results["errors"].append(f"Directory not found: {root_dir}")
            return results

        # Scan recursively for SKILL.md files
        skill_files = list(root_path.rglob("SKILL.md"))
        results["total_found"] = len(skill_files)

        for skill_md in skill_files:
            folder = skill_md.parent

            # Phase 5: Calculate relative namespace from root_dir
            # e.g., root_dir/os/macos/click/SKILL.md -> namespace "os/macos"
            try:
                namespace = str(folder.parent.relative_to(root_path))
                if namespace == ".":
                    namespace = "misc"
            except ValueError:
                namespace = "misc"

            try:
                success = await SkillImporter.import_single_skill(folder, namespace=namespace)
                if success:
                    results["imported"] += 1
                else:
                    results["skipped"] += 1
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                logger.error(f"Failed to import skill from {folder}: {e}")
                results["errors"].append(f"{folder.name}: {str(e)}")

        return results

    @staticmethod
    async def import_single_skill(skill_folder: Path, namespace: str = "misc") -> bool:
        """
        Import a single skill package from a folder.
        """
        # 1. Validate with SkillValidator
        validation = SkillValidator.validate_folder(skill_folder)
        if not validation.is_valid:
            logger.warning(f"Skill validation failed for {skill_folder}: {validation.errors}")
            return False

        metadata = validation.metadata
        # instructions are parsed inside SkillValidator's metadata-returning internal method, but SkillValidator also has _parse_skill_md
        _, instructions = SkillValidator._parse_skill_md(skill_folder / "SKILL.md")

        async with session_scope() as db:
            # Check if skill already exists
            stmt = select(LearnedSkill).where(LearnedSkill.name == metadata["name"])
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if existing:
                if existing.status == "pending_review":
                    # Synthesized skills awaiting user confirmation are owned by
                    # the synthesis route: a file-watcher re-import round trip
                    # (the route's own SKILL.md export echoing back) must not
                    # touch status, activation, or the verification report.
                    logger.info(
                        f"[Importer] Skill '{existing.name}' is pending_review; "
                        "skipping file-watcher update"
                    )
                    return True
                # Update existing skill
                existing.description = metadata.get("description", "")
                existing.namespace = metadata.get("namespace", namespace)
                existing.instructions = instructions
                existing.resource_path = str(skill_folder.absolute())
                existing.trigger_patterns = [metadata["name"]] + (metadata.get("trigger_patterns", []))
                existing.parameters = metadata.get("parameters", [])
                existing.tools_used = _extract_tools_required(metadata)
                existing.status = "verified" if validation.status == "healthy" else "candidate"
                existing.is_active = True
                existing.validation_report = validation.model_dump()
            else:
                # Create new skill
                new_skill = LearnedSkill(
                    name=metadata["name"],
                    description=metadata.get("description", ""),
                    namespace=metadata.get("namespace", namespace),
                    instructions=instructions,
                    resource_path=str(skill_folder.absolute()),
                    trigger_patterns=[metadata["name"]] + (metadata.get("trigger_patterns", [])),
                    parameters=metadata.get("parameters", []),
                    tools_used=_extract_tools_required(metadata),
                    status="verified" if validation.status == "healthy" else "candidate",
                    is_active=True,
                    skill_source="imported",
                    validation_report=validation.model_dump()
                )
                db.add(new_skill)

            await db.flush()
            return True
