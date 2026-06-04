import logging
import os
from typing import List, Optional, Tuple

from app.core.file.verification import (
    safe_read_with_hash,
    write_file_with_verification,
)
from .engine import EditEngine
from .algorithms import calculate_confidence, generate_unified_diff
from .models import MatchConfidence, EditPreviewResult, FileEditOperation

logger = logging.getLogger(__name__)


class FileEditorService:
    """
    Orchestrates file editing operations including fuzzy matching,
    multi-edit atomicity, and diff generation.
    """

    @staticmethod
    async def preview_edit(
        path: str,
        target: str,
        replacement: str,
        absolute_path: str
    ) -> EditPreviewResult:
        """Preview an edit without applying changes."""
        try:
            # Read file content
            file_content, encoding, stats = safe_read_with_hash(absolute_path)
        except Exception as e:
            return EditPreviewResult(
                success=False,
                confidence=MatchConfidence.NONE,
                diff="",
                original_content="",
                new_content="",
                message=f"Failed to read file: {e}"
            )

        if not file_content:
            return EditPreviewResult(
                success=False,
                confidence=MatchConfidence.NONE,
                diff="",
                original_content="",
                new_content="",
                message="File is empty"
            )

        # Try to apply replacement using EditEngine
        success, new_content, log = EditEngine.apply_replacement(
            content=file_content,
            old_string=target,
            new_string=replacement,
            replace_all=False
        )

        if not success:
            return EditPreviewResult(
                success=False,
                confidence=MatchConfidence.NONE,
                diff="",
                original_content=file_content,
                new_content="",
                message=f"Could not find target text. {log}"
            )

        # Extract strategy name from log
        strategy_used = None
        if "strategy:" in log.lower():
            strategy_used = log.split(":")[-1].strip()

        # Check if exact match
        is_exact = target in file_content
        match_count = file_content.count(target) if is_exact else 1

        # Calculate confidence
        confidence = calculate_confidence(
            strategy_name=strategy_used or "unknown",
            is_exact_match=is_exact,
            match_count=match_count
        )

        # Generate diff
        diff = generate_unified_diff(
            original=file_content,
            modified=new_content,
            file_path=path
        )

        return EditPreviewResult(
            success=True,
            confidence=confidence,
            diff=diff,
            original_content=file_content,
            new_content=new_content,
            matched_text=target if is_exact else None,
            strategy_used=strategy_used,
            message=log
        )

    @staticmethod
    async def apply_edits(
        absolute_path: str,
        edits: List[FileEditOperation],
        expected_hash: Optional[str] = None,
        display_path: Optional[str] = None
    ) -> dict:
        """
        Apply multiple edits to a single file atomically.
        
        Returns:
            dict: {
                "success": bool,
                "message": str,
                "new_hash": str | None,
                "applied_edits": int,
                "log": str | None
            }
        """
        display_path = display_path or absolute_path

        try:
            # Read current content and hash
            file_content, _, stats = safe_read_with_hash(absolute_path)

            # Early hash verification
            if expected_hash and stats.content_hash != expected_hash:
                return {
                    "success": False,
                    "message": "File was modified by another process since last read.",
                    "details": f"Current hash: {stats.content_hash[:8]}... Expected: {expected_hash[:8]}..."
                }

            # Phase 1: Validate all edits in memory (dry run)
            current_content = file_content
            logs = []

            for i, edit in enumerate(edits):
                if getattr(edit, "mode", "replace") == "append":
                    new_content = current_content + edit.replacement
                    success = True
                    log = "Appended to end of file"
                elif getattr(edit, "mode", "replace") == "prepend":
                    new_content = edit.replacement + current_content
                    success = True
                    log = "Prepended to beginning of file"
                else:
                    # Try to apply this edit to current content
                    success, new_content, log = EditEngine.apply_replacement(
                        current_content,
                        edit.target,
                        edit.replacement,
                        replace_all=edit.allow_multiple
                    )

                if not success:
                    return {
                        "success": False,
                        "message": f"Edit #{i+1} failed validation. No changes applied to file.",
                        "details": f"Target: {edit.target[:50]}... Error: {log}"
                    }

                logs.append(log)
                current_content = new_content

            # Phase 2: Atomic write
            write_result = write_file_with_verification(
                current_content,
                absolute_path,
                expected_hash=expected_hash
            )

            if not write_result["success"]:
                return {
                    "success": False,
                    "message": f"All {len(edits)} edits validated but write failed.",
                    "details": write_result.get('message')
                }

            return {
                "success": True,
                "message": f"Successfully applied {len(edits)} edit(s) to {display_path}",
                "new_hash": write_result.get("new_hash"),
                "applied_edits": len(edits),
                "log": "\n".join(logs)
            }

        except Exception as e:
            logger.error(f"Failed to apply edits to {absolute_path}: {e}")
            return {
                "success": False,
                "message": f"An unexpected error occurred while editing file.",
                "details": str(e)
            }
