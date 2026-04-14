import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class ValidationMetadata(DynamicBaseModel):
    """Dynamic metadata from skill validation."""


class ValidationResult(BaseModel):
    is_valid: bool
    status: str  # "healthy", "warning", "error"
    errors: list[str] = []
    warnings: list[str] = []
    metadata: ValidationMetadata | None = None


class SkillValidator:
    """
    Validates a skill folder against the 'Anatomy of a Skill' standard.
    """

    REQUIRED_FILES = ["SKILL.md"]
    RECOMMENDED_DIRS = ["scripts", "references", "assets"]

    @classmethod
    def validate_folder(cls, folder_path: Path) -> ValidationResult:
        """
        Perform a comprehensive validation of a skill folder.
        """
        errors = []
        warnings = []

        if not folder_path.exists() or not folder_path.is_dir():
            return ValidationResult(
                is_valid=False,
                status="error",
                errors=[f"Directory does not exist: {folder_path}"]
            )

        # 1. Check for required files
        for req in cls.REQUIRED_FILES:
            if not (folder_path / req).exists():
                errors.append(f"Missing required file: {req}")

        if errors:
            return ValidationResult(is_valid=False, status="error", errors=errors)

        # 2. Validate SKILL.md content and frontmatter
        skill_md_path = folder_path / "SKILL.md"
        metadata, instructions = cls._parse_skill_md(skill_md_path)

        if not metadata:
            errors.append("Invalid or missing YAML frontmatter in SKILL.md")
        else:
            if "name" not in metadata:
                errors.append("Missing 'name' in skill metadata")
            if "description" not in metadata:
                warnings.append("Missing 'description' in skill metadata")

        # 3. Check for recommended structure
        for r_dir in cls.RECOMMENDED_DIRS:
            if not (folder_path / r_dir).exists():
                # Non-critical, just a tip for standardization
                pass
            elif not (folder_path / r_dir).is_dir():
                errors.append(f"'{r_dir}' exists but is not a directory")

        # 4. Check for clutter (Standardization rule: No README, INSTALL etc.)
        clutter_files = ["README.md", "INSTALL.md", "CHANGELOG.md"]
        for clutter in clutter_files:
            if (folder_path / clutter).exists():
                warnings.append(f"Clutter detected: {clutter} should be removed for standardization")

        status = "healthy"
        if errors:
            status = "error"
        elif warnings:
            status = "warning"

        return ValidationResult(
            is_valid=len(errors) == 0,
            status=status,
            errors=errors,
            warnings=warnings,
            metadata=metadata
        )

    @staticmethod
    def _parse_skill_md(file_path: Path) -> tuple[dict | None, str]:
        """
        Internal parser for SKILL.md.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None, content

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None, content

            metadata = yaml.safe_load(parts[1])
            instructions = parts[2].strip()
            return metadata, instructions
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return None, ""
