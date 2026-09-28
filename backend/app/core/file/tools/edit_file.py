import logging
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.file.editor import (
    EditFileRequest,
    EditPreviewResult,
    FileEditOperation,
    FileEditorService,
)
from app.core.tools import get_working_directory
from app.core.tools.base import InjectedToolArg
from app.i18n.service import i18n

from .utils import resolve_and_validate_path

logger = logging.getLogger(__name__)


async def handle_multi_edit(
    path: str,
    edits: list[FileEditOperation],
    expected_hash: str | None,
    verify_types: bool,
    config: RunnableConfig | None,
) -> str:
    """
    Perform multiple edits to a single file atomically.
    Delegates to FileEditorService.
    """
    from app.domain.codebase.exploration.engine import get_exploration_engine
    from app.utils.template import render_template

    try:
        target_path = await resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    result = await FileEditorService.apply_edits(
        absolute_path=target_path,
        edits=edits,
        expected_hash=expected_hash,
        display_path=path,
    )

    if not result["success"]:
        return render_template(
            "domain/tools/edit_result.prompt.j2",
            success=False,
            path=path,
            message=result["message"],
            details=result.get("details", ""),
            labels=i18n.get("domain_tools.files.edit_labels") or {},
        )

    # Success path
    template_context = {
        "success": True,
        "path": path,
        "edit_count": result["applied_edits"],
        "new_hash": result.get("new_hash", "")[:8] if result.get("new_hash") else None,
        "diagnostics": None,
        "labels": i18n.get("domain_tools.files.edit_labels") or {},
    }

    # Optional Semantic Validation
    if verify_types:
        diagnostics = None
        try:
            engine = get_exploration_engine()
            repo_path = get_working_directory(config)
            diagnostics = await engine.check_types(target_path, repo_path)
        except Exception as e:
            logger.debug(f"[Type Check] Failed: {e}", exc_info=True)
        template_context["diagnostics"] = diagnostics

    return render_template(
        "domain/tools/multi_edit_success.prompt.j2", **template_context
    ), {"count": result["applied_edits"]}


async def handle_edit(request: EditFileRequest) -> str:
    """
    Edit file with cascading fuzzy matching.
    Delegates to FileEditorService.
    """
    from app.domain.codebase.exploration.engine import get_exploration_engine
    from app.utils.template import render_template

    try:
        target_path = await resolve_and_validate_path(request.path, request.config)
    except ValueError as e:
        return str(e)

    # Convert single edit to multi-edit list for service
    edits = [
        FileEditOperation(
            target=request.target or "",
            replacement=request.content,
            allow_multiple=request.allow_multiple,
            mode=request.mode,
            start_line=request.start_line,
            end_line=request.end_line,
        )
    ]

    result = await FileEditorService.apply_edits(
        absolute_path=target_path,
        edits=edits,
        expected_hash=request.expected_hash,
        display_path=request.path,
    )

    template_context = {
        "success": result["success"],
        "path": request.path,
        "replaced_count": result.get("applied_edits", 0),
        "new_hash": result.get("new_hash", "")[:8] if result.get("new_hash") else None,
        "diagnostics": None,
        "message": result.get("message"),
        "log": f"Technical details: {result.get('log')}"
        if result.get("log")
        else result.get("details"),
        "causes": [
            c.format(path=request.path)
            for c in (i18n.get("domain_tools.files.edit_causes") or [])
        ],
        "hints": [
            h.format(path=request.path)
            for h in (i18n.get("domain_tools.files.edit_hints") or [])
        ],
        "labels": i18n.get("domain_tools.files.edit_labels") or {},
    }

    if result["success"] and request.verify_types:
        diagnostics = None
        try:
            engine = get_exploration_engine()
            repo_path = get_working_directory(request.config)
            diagnostics = await engine.check_types(target_path, repo_path)
        except Exception as e:
            logger.debug(f"[Type Check] Failed: {e}", exc_info=True)
        template_context["diagnostics"] = diagnostics

    return render_template("domain/tools/edit_result.prompt.j2", **template_context)


def format_preview_result(
    result: EditPreviewResult, path: str, target: str, replacement: str
) -> str:
    """Format preview result for display."""
    from app.utils.template import render_template

    if not result.success:
        return render_template(
            "domain/tools/edit_preview.prompt.j2",
            success=False,
            message="Preview failed",
            details=result.message,
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
        replacement_preview=f"{replacement[:50]}{'...' if len(replacement) > 50 else ''}",
    )


async def edit_file(
    path: str,
    target: str | None = None,
    replacement: str | None = None,
    append: str | None = None,
    prepend: str | None = None,
    edits: list[dict] | None = None,
    allow_multiple: bool = False,
    start_line: int | None = None,
    end_line: int | None = None,
    expected_hash: str | None = None,
    dry_run: bool = False,
    verify_types: bool = True,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    对文件做字符串替换（带自动级联模糊匹配），或追加/前置内容。使用本工具前
    请先调用 read_file 查看文件内容。

    Args:
        path: 要编辑的文件路径。
        target: 要查找并替换的文本。若提供 append/prepend 则可省略。
        replacement: 替换 target 的新文本。若提供 append/prepend 则可省略。
        append: 追加到文件末尾的内容。
        prepend: 前置到文件开头的内容。
        edits: 批量编辑的 dict 列表。每个 dict 可含 'target'、'replacement'、'allow_multiple'、
               'mode'、'start_line'、'end_line'。
        allow_multiple: 替换 target 的所有出现。
        start_line: 可选。target 文本起始行（从 1 开始）。与 end_line 一起提供时限定搜索范围。
        end_line: 可选。结束行号（从 1 开始，含）。
        expected_hash: 可选，乐观并发用的哈希。
        dry_run: 为 True 时只返回预览、不实际改动。
        verify_types: 为 True 时在编辑后做类型检查。

    Examples:
        edit_file(path="file.txt", target="old", replacement="new")
        edit_file(path="file.txt", append="\\nnew line at the end")
        edit_file(path="file.txt", edits=[{"target": "old1", "replacement": "new1"}, {"mode": "append", "replacement": "end"}])
    """
    # Multi-edit mode
    if edits:
        if not path:
            return "SYSTEM ERROR: You MUST provide 'path'."

        edit_models = [
            FileEditOperation.model_validate(e) if isinstance(e, dict) else e
            for e in edits
        ]
        return await handle_multi_edit(
            path=path,
            edits=edit_models,
            expected_hash=expected_hash,
            verify_types=verify_types,
            config=config,
        )

    # Single-edit mode
    mode = "replace"
    final_target = target
    final_replacement = replacement

    if append is not None:
        mode = "append"
        final_replacement = append
        final_target = ""
    elif prepend is not None:
        mode = "prepend"
        final_replacement = prepend
        final_target = ""

    if not path or final_replacement is None:
        return "SYSTEM ERROR: You MUST provide 'path' and either 'replacement' (with 'target'), 'append', or 'prepend'."

    # If dry_run, use preview functionality
    if dry_run:
        try:
            target_path = await resolve_and_validate_path(path, config)
            result = await FileEditorService.preview_edit(
                path=path,
                target=target,
                replacement=replacement,
                absolute_path=target_path,
            )
            return format_preview_result(result, path, target, replacement)
        except Exception as e:
            return f"Preview error: {e}"

    return await handle_edit(
        EditFileRequest(
            path=path,
            target=final_target,
            content=final_replacement,
            allow_multiple=allow_multiple,
            mode=mode,
            start_line=start_line,
            end_line=end_line,
            expected_hash=expected_hash,
            verify_types=verify_types,
            config=config,
        )
    )
