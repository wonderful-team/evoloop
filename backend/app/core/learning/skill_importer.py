import os
import yaml
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.models.learning import LearnedSkill
from app.infrastructure.database.sql.database import session_scope
from sqlalchemy import select
from app.core.learning.skill_validator import SkillValidator

logger = logging.getLogger(__name__)


class SkillImporter:
    """
    Service to import external skill packages (SKILL.md) into the Evoloop database.
    """

    @staticmethod
    async def import_from_directory(root_dir: str) -> Dict[str, Any]:
        """
        Scan a directory for skill folders and import them.
        Each folder must contain a SKILL.md file.
        """
        results = {
            "total_found": 0,
            "imported": 0,
            "skipped": 0,
            "errors": []
        }

        root_path = Path(root_dir)
        if not root_path.exists():
            results["errors"].append(f"Directory not found: {root_dir}")
            return results

        # Scan subdirectories
        skill_folders = [p for p in root_path.iterdir() if p.is_dir()]
        results["total_found"] = len(skill_folders)

        for folder in skill_folders:
            skill_md = folder / "SKILL.md"
            if not skill_md.exists():
                results["skipped"] += 1
                continue

            # Phase 5: Calculate relative namespace from root_dir
            # e.g., root_dir/os/macos/click -> namespace "os/macos"
            namespace = str(folder.parent.relative_to(root_path))
            if namespace == ".":
                namespace = "misc"

            try:
                success = await SkillImporter.import_single_skill(folder, namespace=namespace)
                if success:
                    results["imported"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
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

        # 2. Map Resources
        resource_map = {
            "scripts": [str(p.relative_to(skill_folder)) for p in (skill_folder / "scripts").glob("**/*") if p.is_file()] if (skill_folder / "scripts").exists() else [],
            "references": [str(p.relative_to(skill_folder)) for p in (skill_folder / "references").glob("**/*") if p.is_file()] if (skill_folder / "references").exists() else [],
            "assets": [str(p.relative_to(skill_folder)) for p in (skill_folder / "assets").glob("**/*") if p.is_file()] if (skill_folder / "assets").exists() else []
        }

        async with session_scope() as db:
            # Check if skill already exists
            stmt = select(LearnedSkill).where(LearnedSkill.name == metadata["name"])
            existing = (await db.execute(stmt)).scalar_one_or_none()

            if existing:
                # Update existing skill
                existing.description = metadata.get("description", "")
                existing.namespace = metadata.get("namespace", namespace)
                existing.instructions = instructions
                existing.resource_path = str(skill_folder.absolute())
                existing.trigger_patterns = json.dumps([metadata["name"]] + (metadata.get("trigger_patterns", [])))
                existing.parameters = json.dumps(metadata.get("parameters", []))
                existing.status = "verified" if validation.status == "healthy" else "candidate"
                existing.validation_report = validation.dict()
            else:
                # Create new skill
                new_skill = LearnedSkill(
                    name=metadata["name"],
                    description=metadata.get("description", ""),
                    namespace=metadata.get("namespace", namespace),
                    instructions=instructions,
                    resource_path=str(skill_folder.absolute()),
                    trigger_patterns=json.dumps([metadata["name"]] + (metadata.get("trigger_patterns", []))),
                    parameters=json.dumps(metadata.get("parameters", [])),
                    status="verified" if validation.status == "healthy" else "candidate",
                    is_active=True,
                    validation_report=validation.dict()
                )
                db.add(new_skill)

            await db.flush()
            return True

    @staticmethod
    def _parse_skill_md(content: str) -> tuple[Optional[Dict], str]:
        """
        Parse SKILL.md into metadata (dict) and instructions (markdown string).
        """
        if not content.startswith("---"):
            return None, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None, content

        try:
            metadata = yaml.safe_load(parts[1])
            instructions = parts[2].strip()
            return metadata, instructions
        except Exception as e:
            logger.error(f"Failed to parse YAML frontmatter: {e}")
            return None, content
