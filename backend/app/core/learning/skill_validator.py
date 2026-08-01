import logging
import re
from pathlib import Path

import yaml

from app.core.learning.schemas import ValidationResult

logger = logging.getLogger(__name__)


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
    def _fix_yaml_frontmatter(yaml_text: str) -> str:
        """
        Auto-fix common YAML syntax errors in LLM-generated frontmatter.
        
        Common issues:
        - Unquoted scalar values containing ': ' (colon + space)
        - Unquoted values starting with '#'
        """
        lines = yaml_text.split('\n')
        fixed_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip empty lines, comments, document separators
            if not stripped or stripped.startswith('#') or stripped == '---':
                fixed_lines.append(line)
                continue
            
            # Skip list items (lines starting with '- ')
            if stripped.startswith('- '):
                fixed_lines.append(line)
                continue
            
            # Match key: value pattern
            # Capture indent, key, and the rest as value
            match = re.match(r'^(\s*)(\w+):\s*(.*)$', line)
            if not match:
                fixed_lines.append(line)
                continue
            
            indent, key, value = match.groups()
            
            # Skip if no value after colon
            if not value:
                fixed_lines.append(line)
                continue
            
            # Skip if already quoted
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                fixed_lines.append(line)
                continue
            
            # Skip if value looks like a nested mapping start (e.g., "foo: bar")
            if re.match(r'^\w+:\s', value):
                fixed_lines.append(line)
                continue
            
            # Skip if value is a list or dict literal
            if value.startswith('[') or value.startswith('{') or value.startswith('-'):
                fixed_lines.append(line)
                continue
            
            # Fix unquoted values containing ': ' which breaks YAML parsing
            if ': ' in value:
                # Escape existing double quotes
                escaped_value = value.replace('"', '\\"')
                line = f'{indent}{key}: "{escaped_value}"'
                logger.debug(f"[SkillValidator] Auto-quoted value for key '{key}'")
            
            # Fix unquoted values starting with '#' which YAML treats as comments
            elif value.startswith('#'):
                escaped_value = value.replace('"', '\\"')
                line = f'{indent}{key}: "{escaped_value}"'
                logger.debug(f"[SkillValidator] Auto-quoted comment-like value for key '{key}'")
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    @staticmethod
    def _parse_skill_md(file_path: Path) -> tuple[dict | None, str]:
        """
        Internal parser for SKILL.md.
        
        Tries to parse YAML frontmatter. If initial parse fails due to common
        LLM-generated syntax errors, attempts auto-fix and retries.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None, content

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None, content

            frontmatter_text = parts[1]
            instructions = parts[2].strip()
            
            # First attempt: parse as-is
            try:
                metadata = yaml.safe_load(frontmatter_text)
                if isinstance(metadata, dict):
                    # Check if any string values were incorrectly parsed as None
                    # (e.g., unquoted values starting with '#' are treated as comments)
                    needs_fix = any(
                        metadata.get(k) is None 
                        for k in ["name", "description", "namespace"]
                    )
                    if not needs_fix:
                        return metadata, instructions
            except yaml.YAMLError as e:
                logger.warning(f"[SkillValidator] Initial YAML parse failed for {file_path}: {e}")
            
            # Second attempt: auto-fix common LLM errors and retry
            fixed_frontmatter = SkillValidator._fix_yaml_frontmatter(frontmatter_text)
            try:
                metadata = yaml.safe_load(fixed_frontmatter)
                if isinstance(metadata, dict):
                    logger.info(f"[SkillValidator] Auto-fixed YAML frontmatter for {file_path}")
                    return metadata, instructions
            except yaml.YAMLError as e2:
                logger.error(f"[SkillValidator] Auto-fix failed for {file_path}: {e2}")
            
            # Both attempts failed
            return None, instructions
            
        except Exception as e:
            logger.error(f"[SkillValidator] Failed to parse {file_path}: {e}")
            return None, ""
