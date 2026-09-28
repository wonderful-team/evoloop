"""File facade tool — single unified entry for file read/write/edit/list/move/delete.

2026-09 工具面收敛：``read``/``write``/``edit``/``list_dir``/``move_file``/``delete_file``
六个同域工具收敛为单一 ``file`` 工具，按 ``action`` 分发（对齐 plan/tasks/macro facade
范式与 OpenHands file_editor 单工具形态）。原实现保留为各模块的业务函数，本模块
只做 action 分发与参数透传——路径沙箱（resolve_and_validate_path）、delete 的
confirm 门、Rewind 记账语义全部不变。
"""

from typing import Annotated, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

from .delete_file import delete_file as _delete_impl
from .edit_file import edit_file as _edit_impl
from .list_dir import DEFAULT_MAX_ENTRIES
from .list_dir import list_dir as _list_impl
from .move_file import move_file as _move_impl
from .read_file import read_file as _read_impl
from .write_file import write_file as _write_impl


@evoloop_tool(
    name="file",
    is_state_mutating=True,
    affected_path_keys=["path", "source", "destination"],
    summary_template="evoloop.tool_summary.file",
)
async def file(
    action: Literal["read", "write", "edit", "list", "move", "delete"] = "read",
    path: str | None = None,
    content: str | None = None,
    start_line: int | str | None = None,
    end_line: int | str | None = None,
    include_metadata: bool = True,
    target: str | None = None,
    replacement: str | None = None,
    append: str | None = None,
    prepend: str | None = None,
    edits: list[dict] | None = None,
    allow_multiple: bool = False,
    expected_hash: str | None = None,
    dry_run: bool = False,
    verify_types: bool = True,
    tree: bool = False,
    depth: int = 1,
    filter: str | None = None,
    stats: bool = True,
    with_symbols: bool = False,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    mode: str | None = None,
    source: str | None = None,
    destination: str | None = None,
    overwrite: bool = False,
    confirm: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一文件操作入口——读/写/编辑/列目录/移动/删除。

    Actions（参数按 action 取用）:
    - read:   读文件（默认前 1000 行，start_line/end_line 分段；传目录路径则
              直接列出条目）。参数：path, start_line, end_line, include_metadata。
    - write:  创建新文件（已有文件请用 edit）。参数：path, content。
    - edit:   字符串替换/追加/前置/批量编辑（先 read 再 edit）。参数：path,
              target, replacement, append, prepend, edits, allow_multiple,
              start_line, end_line, expected_hash, dry_run, verify_types。
    - list:   浏览目录（flat/tree、filter、stats）。参数：path, tree, depth,
              filter, stats, with_symbols, max_entries。
    - move:   移动/重命名文件或目录。参数：source, destination, overwrite。
    - delete: 删除文件或目录（**必须 confirm=True**，可经 Rewind 撤销）。
              参数：path, confirm。

    Examples:
        file(action="read", path="main.py")
        file(action="write", path="src/new.py", content="print('hello')")
        file(action="edit", path="a.py", target="old", replacement="new")
        file(action="edit", path="a.py", edits=[{"target": "x", "replacement": "y"}])
        file(action="list", path="src/", tree=True, depth=2)
        file(action="move", source="old.py", destination="new.py")
        file(action="delete", path="temp.py", confirm=True)
    """
    if action == "read":
        return await _read_impl(
            path=path,
            start_line=start_line,
            end_line=end_line,
            include_metadata=include_metadata,
            config=config,
        )
    if action == "write":
        return await _write_impl(path=path, content=content, config=config)
    if action == "edit":
        return await _edit_impl(
            path=path,
            target=target,
            replacement=replacement,
            append=append,
            prepend=prepend,
            edits=edits,
            allow_multiple=allow_multiple,
            start_line=start_line,
            end_line=end_line,
            expected_hash=expected_hash,
            dry_run=dry_run,
            verify_types=verify_types,
            config=config,
        )
    if action == "list":
        return await _list_impl(
            path=path,
            tree=tree,
            depth=depth,
            filter=filter,
            stats=stats,
            with_symbols=with_symbols,
            max_entries=max_entries,
            mode=mode,
            config=config,
        )
    if action == "move":
        return await _move_impl(
            source=source,
            destination=destination,
            overwrite=overwrite,
            config=config,
        )
    if action == "delete":
        return await _delete_impl(path=path, confirm=confirm, config=config)
    return f"Error: unknown file action '{action}'."
