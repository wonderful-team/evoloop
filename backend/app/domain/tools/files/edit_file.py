import difflib
import os
from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.domain.tools.utils.editing.engine import EditEngine
from app.i18n.service import i18n
from app.utils.file import (
    apply_edit_with_verification,
    safe_read_with_hash,
    write_file_with_verification,
)
from app.utils.file import get_file_stats

from .utils import resolve_and_validate_path


class MatchConfidence(Enum):
    """Confidence level for text matching."""
    HIGH = "high"  # Exact match or very close
    MEDIUM = "medium"  # Fuzzy match successful
    LOW = "low"  # Multiple candidates or partial match
    NONE = "none"  # No match found


@dataclass
class EditPreviewResult:
    """Result of previewing an edit."""
    success: bool
    confidence: MatchConfidence
    diff: str
    original_content: str
    new_content: str
    matched_text: str | None
    strategy_used: str | None
    message: str


def generate_unified_diff(
    original: str,
    modified: str,
    file_path: str = "file",
    context_lines: int = 3
) -> str:
    """Generate unified diff format."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    # Ensure lines end with newline for proper diff
    if original_lines and not original_lines[-1].endswith('\n'):
        original_lines[-1] += '\n'
    if modified_lines and not modified_lines[-1].endswith('\n'):
        modified_lines[-1] += '\n'

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines
    )

    return ''.join(diff)


def calculate_confidence(
    strategy_name: str,
    is_exact_match: bool,
    match_count: int,
    similarity_score: float = 1.0
) -> MatchConfidence:
    """Calculate confidence level based on matching strategy and results."""
    if is_exact_match and match_count == 1:
        return MatchConfidence.HIGH

    if match_count > 1:
        return MatchConfidence.LOW

    if strategy_name == "simple_replacer":
        return MatchConfidence.HIGH

    if similarity_score >= 0.8:
        return MatchConfidence.HIGH
    elif similarity_score >= 0.5:
        return MatchConfidence.MEDIUM
    else:
        return MatchConfidence.LOW


async def preview_edit_internal(
    path: str,
    target: str,
    replacement: str,
    config: RunnableConfig | None = None
) -> EditPreviewResult:
    """Internal function to preview edit without applying changes."""
    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content="",
            new_content="",
            matched_text=None,
            strategy_used=None,
            message=f"Path error: {e}"
        )

    # Read file content
    try:
        file_content, encoding, stats = safe_read_with_hash(target_path)
    except Exception as e:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content="",
            new_content="",
            matched_text=None,
            strategy_used=None,
            message=f"Failed to read file: {e}"
        )

    if not file_content:
        return EditPreviewResult(
            success=False,
            confidence=MatchConfidence.NONE,
            diff="",
            original_content="",
            new_content="",
            matched_text=None,
            strategy_used=None,
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
            matched_text=None,
            strategy_used=None,
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


async def handle_edit(
    path: str,
    target: str | None = None,
    content: str | None = None,
    allow_multiple: bool = False,
    expected_hash: str | None = None,
    verify_types: bool = True,
    config: RunnableConfig | None = None,
) -> str:
    """
    Edit file with optional hash verification for concurrent modification detection.
    """
    from app.utils import render_template

    if not target and not content:
        return i18n.get("domain_tools.files.edit_args_required")

    # Safety Check: Target Uniqueness
    if len(target.strip()) < 3:
        return i18n.get("domain_tools.files.edit_target_short")

    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return i18n.get("domain_tools.files.edit_not_found", path=path)

    try:
        from app.domain.codebase.exploration.engine import get_exploration_engine

        # Use new verification-based edit
        result = apply_edit_with_verification(
            file_path=target_path,
            old_string=target,
            new_string=content,
            expected_hash=expected_hash,
            allow_multiple=allow_multiple
        )

        template_context = {
            "success": result["success"],
            "path": path,
            "replaced_count": result.get("replaced_count", 1),
            "new_hash": result.get("new_hash", "")[:8] if result.get("new_hash") else None,
            "diagnostics": None,
            "message": None,
            "log": None,
            "causes": [],
            "hints": [],
            "labels": i18n.get("domain_tools.files.edit_labels") or {}
        }

        if result["success"]:
            template_context["message"] = i18n.get("domain_tools.files.edit_success", path=path)

            # Optional Semantic Validation
            if verify_types:
                try:
                    engine = get_exploration_engine()
                    repo_path = get_working_directory(config)
                    diagnostics = await engine.check_types(target_path, repo_path)
                    template_context["diagnostics"] = diagnostics
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug(f"Integrated type check failed: {e}")

            return render_template("files/edit_result.prompt.j2", **template_context)
        else:
            error = result.get("error", "UNKNOWN")
            message = result.get("message", "Edit failed")

            if error == "HASH_MISMATCH":
                template_context["message"] = message
                template_context["details"] = (
                    f"Current hash: {result.get('current_hash', 'unknown')[:8]}...\n"
                    f"Expected: {result.get('expected_hash', 'unknown')[:8]}...\n"
                    f"Please re-read the file and try again."
                )
                return render_template("files/edit_result.prompt.j2", **template_context)
            
            elif error == "STRING_NOT_FOUND":
                # Try fuzzy fallback
                file_content, _, stats = safe_read_with_hash(target_path)
                success, new_content, log = EditEngine.apply_replacement(
                    file_content, target, content, replace_all=allow_multiple
                )
                if success:
                    # Write with verification
                    write_result = write_file_with_verification(
                        new_content, target_path, expected_hash=stats.content_hash
                    )
                    if write_result["success"]:
                        template_context.update({
                            "success": True,
                            "message": f"{i18n.get('domain_tools.files.edit_success', path=path)} (fuzzy match)",
                            "log": log
                        })
                        if verify_types:
                            try:
                                engine = get_exploration_engine()
                                repo_path = get_working_directory(config)
                                template_context["diagnostics"] = await engine.check_types(target_path, repo_path)
                            except Exception:
                                pass
                        return render_template("files/edit_result.prompt.j2", **template_context)
                    else:
                        return f"⚠️ Fuzzy match succeeded but write failed: {write_result.get('message')}"

                # Strict fail report using i18n
                template_context.update({
                    "success": False,
                    "message": template_context["labels"].get("strict_fail", "EDIT FAILED: Could not find the target text in file."),
                    "log": f"Technical details: {log}",
                    "causes": [c.format(path=path) for c in (i18n.get("domain_tools.files.edit_causes") or [])],
                    "hints": [h.format(path=path) for h in (i18n.get("domain_tools.files.edit_hints") or [])]
                })
                return render_template("files/edit_result.prompt.j2", **template_context)
            
            elif error == "MULTIPLE_OCCURRENCES":
                return i18n.get("domain_tools.files.edit_multiple_found", count=result.get("count", "multiple"))
            else:
                return f"❌ Edit failed: {message}"

    except Exception as e:
        return i18n.get("domain_tools.files.edit_error", error=str(e))


def format_preview_result(result: EditPreviewResult, path: str, target: str, replacement: str) -> str:
    """Format preview result for display."""
    from app.utils import render_template

    if not result.success:
        return render_template(
            "files/edit_preview.prompt.j2",
            success=False,
            message="Preview failed",
            details=result.message
        )

    return render_template(
        "files/edit_preview.prompt.j2",
        success=True,
        path=path,
        message=f"Edit Preview ({result.confidence.value.upper()})",
        strategy=result.strategy_used,
        details=result.message,
        diff=result.diff,
        confidence=result.confidence.value,
        target_preview=f"{target[:50]}{'...' if len(target) > 50 else ''}",
        replacement_preview=f"{replacement[:50]}{'...' if len(replacement) > 50 else ''}"
    )


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.edit_file",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "编辑文件", "en": "Edit File"}
)
async def edit_file(
    path: str | None = None,
    target: str | None = None,
    replacement: str | None = None,
    allow_multiple: bool = False,
    expected_hash: str | None = None,
    dry_run: bool = False,
    verify_types: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Edit a file by replacing a specific block of text.

    Args:
        path: Target file path. **REQUIRED**
        target: The exact text to find. **REQUIRED**
        replacement: The new content. **REQUIRED**
        allow_multiple: If True, replaces ALL occurrences.
        expected_hash: Expected content hash for concurrent modification detection.
                      Get this from read_file output to ensure you're editing the latest version.
        dry_run: If True, preview the change without actually modifying the file.
                 Use this to verify the edit will work as expected.
        verify_types: If True (default), perform a semantic type check after the edit.
                      Requires an active LSP for the language.

    Examples:
        # Preview first (recommended for uncertain edits)
        edit_file(path="src/main.py", target="old()", replacement="new()", dry_run=True)
        
        # Then apply
        edit_file(path="src/main.py", target="old()", replacement="new()")
    """
    # HYPER-ROBUST VALIDATION
    if not path or target is None or replacement is None:
        return (
            "SYSTEM ERROR: You called 'edit_file' with EMPTY arguments. "
            "You MUST provide 'path', 'target', and 'replacement'.\n"
            "CORRECT USAGE: edit_file(path='...', target='...', replacement='...')\n"
            "ACTION: Retry the tool call immediately with correct arguments."
        )

    # If dry_run, use preview functionality
    if dry_run:
        result = await preview_edit_internal(path=path, target=target, replacement=replacement, config=config)
        return format_preview_result(result, path, target, replacement)

    return await handle_edit(path, target, replacement, allow_multiple, expected_hash, verify_types, config=config)
