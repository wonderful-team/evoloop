import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.file.editor import (
    FileEditorService,
    FileEditOperation,
    EditFileRequest,
    EditPreviewResult,
    MatchConfidence,
)
from app.core.tools import evoloop_tool, get_working_directory
from app.i18n.service import i18n
from .utils import resolve_and_validate_path

logger = logging.getLogger(__name__)


async def handle_multi_edit(
    path: str,
    edits: list[FileEditOperation],
    expected_hash: str | None,
    verify_types: bool,
    config: RunnableConfig | None
) -> str:
    """
    Perform multiple edits to a single file atomically.
    Delegates to FileEditorService.
    """
    from app.utils import render_template
    from app.domain.codebase.exploration.engine import get_exploration_engine

    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    result = await FileEditorService.apply_edits(
        absolute_path=target_path,
        edits=edits,
        expected_hash=expected_hash,
        display_path=path
    )

    if not result["success"]:
        return render_template(
            "domain/tools/edit_result.prompt.j2",
            success=False,
            path=path,
            message=result["message"],
            details=result.get("details", ""),
            labels=i18n.get("domain_tools.files.edit_labels") or {}
        )

    # Success path
    template_context = {
        "success": True,
        "path": path,
        "edit_count": result["applied_edits"],
        "new_hash": result.get("new_hash", "")[:8] if result.get("new_hash") else None,
        "diagnostics": None,
        "labels": i18n.get("domain_tools.files.edit_labels") or {}
    }

    # Optional Semantic Validation
    if verify_types:
        diagnostics = None
        try:
            engine = get_exploration_engine()
            repo_path = get_working_directory(config)
            diagnostics = await engine.check_types(target_path, repo_path)
        except Exception as e:
            logger.debug(f"[Type Check] Failed: {e}")
        template_context["diagnostics"] = diagnostics

    return render_template("domain/tools/multi_edit_success.prompt.j2", **template_context), {"count": result["applied_edits"]}


async def handle_edit(request: EditFileRequest) -> str:
    """
    Edit file with cascading fuzzy matching.
    Delegates to FileEditorService.
    """
    from app.utils import render_template
    from app.domain.codebase.exploration.engine import get_exploration_engine

    try:
        target_path = await resolve_and_validate_path(request.path, request.config)
    except ValueError as e:
        return str(e)

    # Convert single edit to multi-edit list for service
    edits = [FileEditOperation(target=request.target, replacement=request.content, allow_multiple=request.allow_multiple)]

    result = await FileEditorService.apply_edits(
        absolute_path=target_path,
        edits=edits,
        expected_hash=request.expected_hash,
        display_path=request.path
    )

    template_context = {
        "success": result["success"],
        "path": request.path,
        "replaced_count": result.get("applied_edits", 0),
        "new_hash": result.get("new_hash", "")[:8] if result.get("new_hash") else None,
        "diagnostics": None,
        "message": result.get("message"),
        "log": f"Technical details: {result.get('log')}" if result.get("log") else result.get("details"),
        "causes": [c.format(path=request.path) for c in (i18n.get("domain_tools.files.edit_causes") or [])],
        "hints": [h.format(path=request.path) for h in (i18n.get("domain_tools.files.edit_hints") or [])],
        "labels": i18n.get("domain_tools.files.edit_labels") or {}
    }

    if result["success"] and request.verify_types:
        diagnostics = None
        try:
            engine = get_exploration_engine()
            repo_path = get_working_directory(request.config)
            diagnostics = await engine.check_types(target_path, repo_path)
        except Exception as e:
            logger.debug(f"[Type Check] Failed: {e}")
        template_context["diagnostics"] = diagnostics

    return render_template("domain/tools/edit_result.prompt.j2", **template_context)


def format_preview_result(result: EditPreviewResult, path: str, target: str, replacement: str) -> str:
    """Format preview result for display."""
    from app.utils import render_template

    if not result.success:
        return render_template(
            "domain/tools/edit_preview.prompt.j2",
            success=False,
            message="Preview failed",
            details=result.message
        )

    return render_template(
        "domain/tools/edit_preview.prompt.j2",
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
    summary_template="evoloop.tool_summary.edit_file",
)
async def edit_file(
    path: str | None = None,
    target: str | None = None,
    replacement: str | None = None,
    edits: list[dict] | None = None,
    allow_multiple: bool = False,
    expected_hash: str | None = None,
    dry_run: bool = False,
    verify_types: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Performs string replacements in files with automatic cascading fuzzy matching.
    [Documentation truncated for brevity but remains same in real file]
    """
    # Multi-edit mode
    if edits:
        if not path:
            return "SYSTEM ERROR: You MUST provide 'path'."
        
        edit_models = [FileEditOperation.model_validate(e) if isinstance(e, dict) else e for e in edits]
        return await handle_multi_edit(
            path=path,
            edits=edit_models,
            expected_hash=expected_hash,
            verify_types=verify_types,
            config=config,
        )

    # Single-edit mode
    if not path or target is None or replacement is None:
        return "SYSTEM ERROR: You MUST provide 'path', 'target', and 'replacement'."

    # If dry_run, use preview functionality
    if dry_run:
        try:
            target_path = await resolve_and_validate_path(path, config)
            result = await FileEditorService.preview_edit(
                path=path,
                target=target,
                replacement=replacement,
                absolute_path=target_path
            )
            return format_preview_result(result, path, target, replacement)
        except Exception as e:
            return f"Preview error: {e}"

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
