import asyncio
import difflib
import logging
import os
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.core.file.editor import EditEngine
from app.core.file import (
    safe_read_with_hash,
    write_file_with_verification,
    get_file_info,  # Replaces get_file_stats
)
from app.i18n.service import i18n
from app.utils.model_helpers import LegacyDictMixin
from .utils import resolve_and_validate_path

logger = logging.getLogger(__name__)

# Keep references to background tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()


class MatchConfidence(Enum):
    """Confidence level for text matching."""
    HIGH = "high"  # Exact match or very close
    MEDIUM = "medium"  # Fuzzy match successful
    LOW = "low"  # Multiple candidates or partial match
    NONE = "none"  # No match found


class EditFileRequest(BaseModel):
    """Request model for editing a file."""
    path: str
    target: str | None = None
    content: str | None = None
    allow_multiple: bool = False
    expected_hash: str | None = None
    verify_types: bool = True
    config: RunnableConfig | None = None


class EditPreviewResult(BaseModel, LegacyDictMixin):
    """Result of previewing an edit."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    confidence: MatchConfidence
    diff: str
    original_content: str
    new_content: str
    matched_text: str | None = None
    strategy_used: str | None = None
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


async def handle_edit(request: EditFileRequest) -> str:
    """
    Edit file with cascading fuzzy matching and optional hash verification.
    """
    from app.utils import render_template

    path = request.path
    target = request.target
    content = request.content
    allow_multiple = request.allow_multiple
    expected_hash = request.expected_hash
    verify_types = request.verify_types
    config = request.config

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

        # Read current content and hash
        file_content, _, stats = safe_read_with_hash(target_path)

        # Early hash verification (fast fail)
        if expected_hash and stats.content_hash != expected_hash:
            template_context = {
                "success": False,
                "path": path,
                "message": "File was modified by another process since last read.",
                "details": (
                    f"Current hash: {stats.content_hash[:8]}...\n"
                    f"Expected: {expected_hash[:8]}...\n"
                    f"Please re-read the file and try again."
                ),
                "labels": i18n.get("domain_tools.files.edit_labels") or {}
            }
            return render_template("files/edit_result.prompt.j2", **template_context)

        # Main path: cascading fuzzy matching via EditEngine
        match_success, new_content, log = EditEngine.apply_replacement(
            file_content, target, content, replace_all=allow_multiple
        )

        template_context = {
            "success": match_success,
            "path": path,
            "replaced_count": 1,
            "new_hash": None,
            "diagnostics": None,
            "message": None,
            "log": None,
            "causes": [],
            "hints": [],
            "labels": i18n.get("domain_tools.files.edit_labels") or {}
        }

        if not match_success:
            # Distinguish multiple occurrences from plain not-found
            if "appears" in log.lower() and "times" in log.lower():
                return i18n.get("domain_tools.files.edit_multiple_found", count="multiple")

            template_context.update({
                "success": False,
                "message": template_context["labels"].get("strict_fail", "EDIT FAILED: Could not find the target text in file."),
                "log": f"Technical details: {log}",
                "causes": [c.format(path=path) for c in (i18n.get("domain_tools.files.edit_causes") or [])],
                "hints": [h.format(path=path) for h in (i18n.get("domain_tools.files.edit_hints") or [])]
            })
            return render_template("files/edit_result.prompt.j2", **template_context)

        # Write with verification (optimistic lock at write time)
        write_result = write_file_with_verification(
            new_content, target_path, expected_hash=expected_hash
        )

        if not write_result["success"]:
            return f"Edit matched but write failed: {write_result.get('message')}"

        template_context.update({
            "success": True,
            "message": i18n.get("domain_tools.files.edit_success", path=path),
            "new_hash": write_result.get("new_hash", "")[:8] if write_result.get("new_hash") else None,
            "log": log
        })

        # Optional Semantic Validation (async)
        if verify_types:
            async def _async_type_check():
                try:
                    engine = get_exploration_engine()
                    repo_path = get_working_directory(config)
                    diagnostics = await engine.check_types(target_path, repo_path)
                    if diagnostics:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(f"[Async Type Check] {path}: {len(diagnostics)} diagnostic(s) found")
                        for d in diagnostics[:3]:
                            logger.info(f"  - {d.get('severity', 'info')}: {d.get('message', '')[:50]}")
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug(f"[Async Type Check] Failed: {e}")

            # Fire and forget - keep reference to prevent GC
            task = asyncio.create_task(_async_type_check())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

            # Add a note that type check is running in background
            template_context["diagnostics"] = [{"severity": "info", "message": "Type check running in background..."}]

        return render_template("files/edit_result.prompt.j2", **template_context)

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
    Performs string replacements in files with automatic cascading fuzzy matching.

    Usage:
    - You MUST use read_file at least once in the conversation before editing.
    - ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
    - The tool uses cascading fuzzy matching (exact -> line-trimmed -> block-anchor -> context-aware -> indentation-flexible).
      Provide enough surrounding context in `target` to ensure uniqueness.
    - If `target` is found multiple times and you don't want to replace all, provide a larger unique block.
    - The edit will FAIL if no matching strategy can locate the target text.

    When to use:
    - Use this for single, isolated changes to one part of a file.
    - For multiple changes to the same file, use multiedit_file instead.
    - For complex multi-block structural changes, use apply_patch_file instead.
    - Do NOT use this tool for auto-generated content (like running formatters); use Bash or Write instead.

    Args:
        path: Target file path. **REQUIRED**
        target: The text to find. Include surrounding lines for uniqueness. **REQUIRED**
        replacement: The new content. **REQUIRED**
        allow_multiple: Replace ALL occurrences of the matched text.
        expected_hash: Optional content hash for concurrent modification detection.
                      Get this from read_file output to ensure you're editing the latest version.
        dry_run: If True, preview the change without actually modifying the file.
                 Only use this for uncertain complex edits; simple edits should be applied directly.
        verify_types: If True (default), perform a semantic type check after the edit.
                      Requires an active LSP for the language.

    Examples:
        # Simple edit (default path)
        edit_file(path="src/main.py", target="def old():", replacement="def new():")
        
        # Preview only for uncertain changes
        edit_file(path="src/main.py", target="old()", replacement="new()", dry_run=True)
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

    return await handle_edit(
        EditFileRequest(
            path=path,
            target=target,
            content=replacement,
            allow_multiple=allow_multiple,
            expected_hash=expected_hash,
            verify_types=verify_types,
            config=config,
        )
    )
