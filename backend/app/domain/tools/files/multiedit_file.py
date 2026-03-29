"""
Multi-edit tool for making multiple edits to a single file in one atomic operation.

This tool allows you to perform multiple find-and-replace operations efficiently.
Prefer this tool over the Edit tool when you need to make multiple edits to the same file.
"""

import asyncio
import os
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool, get_working_directory
from app.domain.tools.utils.editing.engine import EditEngine
from app.i18n.service import i18n
from app.utils.file import safe_read_with_hash, write_file_with_verification

from .utils import resolve_and_validate_path

# Keep references to background tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()


@evoloop_tool(
    is_state_mutating=True,
    affected_path_keys=["path"],
    summary_template="database_logger.tool_summary.multiedit_file",
    result_summary_template="database_logger.tool_summary.file_op_result",
    name_map={"zh": "批量编辑文件", "en": "Multi-Edit File"}
)
async def multiedit_file(
    path: str | None = None,
    edits: list[dict] | None = None,
    expected_hash: str | None = None,
    verify_types: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Make multiple edits to a single file in one atomic operation.

    This is the PREFERRED tool when you need to make several changes to different parts
    of the same file. It is faster and more efficient than calling edit_file multiple times.

    Before using this tool:
    1. Use Read tool to understand the file's contents and context
    2. Verify the directory path is correct

    IMPORTANT:
    - All edits are applied in sequence, in the order they are provided
    - Each edit operates on the result of the previous edit
    - All edits must be valid for the operation to succeed - if any edit fails, NONE will be applied
    - This tool is ideal when you need to make several changes to different parts of the same file

    CRITICAL REQUIREMENTS:
    1. All edits follow the same requirements as the single Edit tool
    2. The edits are atomic - either all succeed or none are applied
    3. Plan your edits carefully to avoid conflicts between sequential operations

    WARNING:
    - The tool will fail if an edit's target doesn't match the file contents
    - Since edits are applied in sequence, ensure that earlier edits don't affect the text that later edits are trying to find
    - Always use absolute file paths (starting with /)

    When making edits:
    - Ensure all edits result in idiomatic, correct code
    - Do not leave the code in a broken state
    - Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.

    If you want to create a new file, use:
    - A new file path, including dir name if needed
    - First edit: empty target and the new file's contents as replacement
    - Subsequent edits: normal edit operations on the created content

    Args:
        path: Target file path. **REQUIRED**
        edits: Array of edit operations to perform sequentially. Each edit contains:
               - target: The text to replace (must match file contents)
               - replacement: The new content
               - allow_multiple: Replace all occurrences of target (optional, default false)
               **REQUIRED**
        expected_hash: Expected content hash for concurrent modification detection.
                      Get this from read_file output to ensure you're editing the latest version.
        verify_types: If True (default), perform a semantic type check after all edits.
                      Requires an active LSP for the language.

    Examples:
        # Multiple edits to the same file
        multiedit_file(
            path="src/app.py",
            edits=[
                {"target": "def foo():", "replacement": "def bar():"},
                {"target": "x = 1", "replacement": "x = 2"},
                {"target": "print('hello')", "replacement": "logger.info('hello')"}
            ]
        )
    """
    from app.utils import render_template
    from app.domain.codebase.exploration.engine import get_exploration_engine

    # Validation
    if not path:
        return (
            "SYSTEM ERROR: You called 'multiedit_file' with EMPTY path. "
            "You MUST provide 'path'.\n"
            "CORRECT USAGE: multiedit_file(path='...', edits=[...])"
        )

    if not edits or not isinstance(edits, list) or len(edits) == 0:
        return (
            "SYSTEM ERROR: You called 'multiedit_file' with INVALID edits. "
            "You MUST provide a non-empty list of edits.\n"
            "CORRECT USAGE: multiedit_file(path='...', edits=[{'target': '...', 'replacement': '...'}])"
        )

    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return i18n.get("domain_tools.files.edit_not_found", path=path)

    try:
        # Read current content and hash
        file_content, _, stats = safe_read_with_hash(target_path)

        # Early hash verification
        if expected_hash and stats.content_hash != expected_hash:
            return render_template(
                "files/edit_result.prompt.j2",
                success=False,
                path=path,
                message="File was modified by another process since last read.",
                details=(
                    f"Current hash: {stats.content_hash[:8]}...\n"
                    f"Expected: {expected_hash[:8]}...\n"
                    f"Please re-read the file and try again."
                ),
                labels=i18n.get("domain_tools.files.edit_labels") or {}
            )

        # Phase 1: Validate all edits in memory (dry run)
        current_content = file_content
        validated_edits = []

        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return f"❌ Edit #{i+1} is not a valid dictionary. Each edit must be {{'target': '...', 'replacement': '...'}}"

            target = edit.get("target", "")
            replacement = edit.get("replacement", "")
            allow_multiple = edit.get("allow_multiple", False)

            # Safety check: target length
            if len(target.strip()) < 3:
                return f"❌ Edit #{i+1}: Target block too short (must be > 2 characters). Provide more context."

            # Try to apply this edit to current content
            success, new_content, log = EditEngine.apply_replacement(
                current_content,
                target,
                replacement,
                replace_all=allow_multiple
            )

            if not success:
                return (
                    f"❌ Edit #{i+1} failed validation. No changes applied to file.\n"
                    f"   Target: {target[:50]}{'...' if len(target) > 50 else ''}\n"
                    f"   Error: {log}\n"
                    f"   (Previous {i} edits would have succeeded, but were not applied due to atomicity)"
                )

            validated_edits.append({
                "index": i + 1,
                "strategy": log.split(":")[-1].strip() if ":" in log else "unknown"
            })
            current_content = new_content

        # Phase 2: Atomic write
        write_result = write_file_with_verification(
            current_content,
            target_path,
            expected_hash=expected_hash
        )

        if not write_result["success"]:
            return f"⚠️ All {len(edits)} edits validated but write failed: {write_result.get('message')}"

        # Build success response
        template_context = {
            "success": True,
            "path": path,
            "edit_count": len(edits),
            "new_hash": write_result.get("new_hash", "")[:8] if write_result.get("new_hash") else None,
            "diagnostics": None,
            "labels": i18n.get("domain_tools.files.edit_labels") or {}
        }

        # Optional Semantic Validation (async - once for all edits)
        if verify_types:
            async def _async_type_check():
                try:
                    engine = get_exploration_engine()
                    repo_path = get_working_directory(config)
                    diagnostics = await engine.check_types(target_path, repo_path)
                    if diagnostics:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(f"[Async Type Check] {path} ({len(edits)} edits): {len(diagnostics)} diagnostic(s)")
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

        return render_template("files/multiedit_success.prompt.j2", **template_context)

    except Exception as e:
        return i18n.get("domain_tools.files.edit_error", error=str(e))
