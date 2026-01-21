import os

from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import DEFAULT_EXCLUDED_DIRS
from app.core.tools import evoloop_tool, get_working_directory
from app.domain.codebase.filter import FileFilter
from app.utils.file import read_file_content as utils_read_file
from app.utils.file import resolve_path
from app.utils.file import write_file_contents as utils_write_file
from app.utils.process import run_command


@evoloop_tool
def list_files(
    path: str = ".",
    recursive: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    List files in a directory.
    By default is non-recursive. Set recursive=True for deep listing (careful with large projects).
    For structural understanding with annotations, prefer `list_files(path, tree=True)` from domain/tools/files.
    """
    """
    List files in a directory using standardized FileFilter logic.
    """
    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))

    if not os.path.exists(target_path):
        return f"Error: Directory does not exist: {target_path}"

    if not recursive:
        # Simple listdir with filter
        try:
            items = os.listdir(target_path)
            # Filter? FileFilter is mostly for files. 
            # But let's basic filter hidden/excluded.
            file_filter = FileFilter()
            filtered_items = []
            for item in items:
                full_p = os.path.join(target_path, item)
                if file_filter.should_include(full_p):
                    filtered_items.append(item)
                elif os.path.isdir(full_p) and item not in DEFAULT_EXCLUDED_DIRS and not item.startswith("."):
                    # Include directories if not explicitly excluded (FileFilter mostly checks files)
                    # But we should mimic its directory logic too.
                    # Simplified:
                    filtered_items.append(item + "/")
            return "\n".join(sorted(filtered_items))
        except Exception as e:
            return f"Error listing files: {e}"

    # Recursive: Use standardized walk_tree
    from app.utils.file import walk_tree

    file_filter = FileFilter()
    results = []

    # Safety limit
    MAX_FILES = 1000
    count = 0

    for full_path in walk_tree(target_path, filter_func=file_filter.should_include):
        # list_files expects relative paths
        rel_path = os.path.relpath(full_path, target_path)
        results.append(rel_path)
        count += 1

        if count >= MAX_FILES:
            results.append(f"... (Truncated at {MAX_FILES} files)")
            return "\n".join(results)

    return "\n".join(sorted(results))


@evoloop_tool
def read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Read the contents of a file. Supports optional line range reading.
    Line numbers are 1-based.
    """
    root = get_working_directory(config)
    target_path = resolve_path(path, base_path=root)

    if not target_path or not os.path.exists(target_path):
        return f"Error: File not found: {path} (Resolved: {target_path})"

    content, _ = utils_read_file(target_path, start_line, end_line)
    return content


@evoloop_tool
def edit_file(
    path: str,
    target: str,
    replacement: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Edit a file by replacing a specific target snippet with a replacement.
    Efficient for making changes without re-writing the whole document.

    Args:
        path: Relative path to the file.
        target: The exact text block to replace. Must be unique in the file.
        replacement: The new text block.
    """
    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))

    if not os.path.exists(target_path):
        return f"Error: File not found: {target_path}"

    with open(target_path, encoding="utf-8") as f:
        content = f.read()

    count = content.count(target)

    if count == 0:
        return "Error: Target snippet not found. Check whitespace/indentation."
    elif count > 1:
        return f"Error: Target snippet found {count} times. Please include more context to make it unique."

    new_content = content.replace(target, replacement)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return f"Successfully edited {path}"


@evoloop_tool
def grep_files(
    pattern: str,
    path: str = ".",
    case_insensitive: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Search for a text pattern in files using 'grep -r'.
    Useful for finding all usages of a function, class, or variable.
    """
    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))

    # grep -r searches everything by default.
    # To use our centralized FileFilter logic with `grep`, we'd ideally pass specific files or multiple --exclude args.
    # `FileFilter` is complex (size, binary, custom rules). `grep` has limited regex/wildcard excludes.
    #
    # Option A: List all files with `os.walk` + `FileFilter`, then grep each (too slow for large codebase).
    # Option B: Translate `FileFilter` logic into `grep` arguments as best as possible.
    #
    # Given the user request to "use FileFilter logic", for `grep_files` (which is a rough search), 
    # relying on `DEFAULT_EXCLUDED_DIRS` is usually close enough to FileFilter's directory logic.
    # But if we want to be strict, we might need to exclusions from FileFilter if it has global state.
    # `FileFilter` currently uses `DEFAULT_EXCLUDED_DIRS` implicitly via `BLACKLIST_DIRS` check in `_is_likely_compressed_file` etc?
    # Actually `FileFilter` checks `exclusions` passed to `should_include`.
    #
    # The user example `AnnotatedTreeGenerator` uses `self.file_filter = FileFilter()` and checks files one by one.
    # grep is a bulk operation.
    #
    # Let's keep using `DEFAULT_EXCLUDED_DIRS` as a robust approximation for grep, 
    # BUT we can add a comment acknowledging the alignment.
    # OR if we want to support `tool.py`'s `list_files` which could use FileFilter?
    # The user specifically mentioned "Unified file filtering logic... refer to AnnotatedTreeGenerator".
    # `list_files` (lines 16-41) currently just runs `ls`. 
    # Let's upgrade `list_files` to use `FileFilter` instead of `ls` if reasonable?
    # `list_files` description says "simple ls". 
    #
    # However, `grep_files` at line 105 is the one I touched.
    # I will stick to the previous `DEFAULT_EXCLUDED_DIRS` fix for `grep_files` as `grep` cannot easily run python logic per file during search.
    #
    # I WILL update `list_files` to use `FileFilter` if specific pattern/recursive is requested, or just respect it is `ls`.
    # Actually, the user's intent "Unified... filter.py" strongly suggests using it where file traversal happens.
    # The `grep_files` tool delegates to `grep` binary for speed. 
    # It seems `find_definition` (analysis/tools.py) falls back to `grep` too.
    #
    # Wait, `AnnotatedTreeGenerator` is for *listing/visualizing* structure. 
    # Maybe the user wants me to apply it to `list_files`?
    #
    # Let's update `list_files` to support smart filtering too?
    # The current `list_files` implementation is `ls`.
    #
    # Actually, look at `app/domain/codebase/analysis/tools.py`.
    # It has `FileFilter`? No.
    #
    # Let's adhere to the instruction: "Unified file filtering... use filter.py".
    # I will assume this applies primarily to where we *iterate* files in Python.
    # The `grep_files` using `grep` CLI is distinct.
    #
    # Let's update `list_files` to be smarter or at least acknowledge `FileFilter`?
    # Or maybe the user meant `analysis/tools.py` logic?
    #
    # Re-reading `grep_files` in `infrastructure/filesystem/tool.py`:
    # It uses `grep -r`. It's hard to inject `FileFilter` there.
    #
    # Let's update `find_definition` in `domain/codebase/analysis/tools.py`? 
    # It also uses `grep`.
    #
    # Perhaps I should leave `grep` logic as "fast path" but update any Python iteration.
    #
    # Wait! The user pointed to `AnnotatedTreeGenerator`.
    # `AnnotatedTreeGenerator` walks directories and checks `self.file_filter.should_include(f_abs)`.
    #
    # If I look at `app/domain/codebase/analysis/tools.py`:
    # It doesn't walk files. It asks Graph or Greps.
    #
    # Maybe I missed a spot? 
    # `app/infrastructure/filesystem/tool.py` has `list_files`.
    # `ls -R` dumps everything including `.git` if not careful (though I added excludes to grep).
    # `ls` tool doesn't use the excludes!
    #
    # Fix: Rewrite `list_files` in `app/infrastructure/filesystem/tool.py` to use `FileFilter` + `os.walk` instead of `ls` command.
    # This aligns perfectly with "Unified Logic".

    cmd = ["grep", "-r", "-n"]
    if case_insensitive:
        cmd.append("-i")

    # Use standard excluded directories
    for excluded_dir in DEFAULT_EXCLUDED_DIRS:
        cmd.append(f"--exclude-dir={excluded_dir}")

    cmd.append(pattern)
    cmd.append(target_path)

    res = run_command(cmd)
    if not res.success:
        # grep returns 1 if no lines found, which run_command might capture as non-zero return code
        # but standardized run_command logic usually handles checking or we check returncode here.
        # run_command returns CommandResult(returncode, stdout, stderr).
        if res.returncode == 1:
            return "No matches found."
        return f"Error running grep: {res.stderr}"

    return res.stdout[:3000]


@evoloop_tool
def write_file_content(path: str, content: str, config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
    """
    Write content to a file.
    """
    root = get_working_directory(config)
    # Use resolve_path but fall back to join if simply creating new file
    target_path = resolve_path(path, base_path=root) or os.path.abspath(os.path.join(root, path))

    utils_write_file(content, target_path)
    return f"Successfully wrote to {target_path}"
