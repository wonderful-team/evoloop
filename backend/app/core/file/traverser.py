import logging
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from app.constants import DEFAULT_EXCLUDED_DIRS

from .filter import is_ignored_path

logger = logging.getLogger(__name__)


@dataclass
class TraverseOptions:
    """Configuration for directory traversal."""

    max_depth: int | None = None
    exclude_dirs: list[str] | None = None
    filter_func: Callable[[str], bool] | None = None
    dir_filter: Callable[[str], bool] | None = None
    include_dirs: bool = False
    recursive: bool = True
    follow_ignore: bool = True
    gitignore_root: str | None = None  # 传入则启用嵌套 .gitignore 过滤；留空时自动探测


class FileTraverser:
    """
    Unified, high-performance file system traverser.
    Single source of truth for all directory walking and listing.
    """

    @staticmethod
    def _resolve_gitignore_root(root_path: str, explicit_root: str | None) -> str | None:
        """Resolve the gitignore root: explicit > auto-detect (walk up)."""
        if explicit_root:
            explicit_root = os.path.abspath(explicit_root)
            if os.path.isfile(os.path.join(explicit_root, ".gitignore")):
                return explicit_root
            return None
        # Auto-detect: walk up from root_path to find nearest .gitignore
        current = os.path.abspath(root_path)
        while True:
            if os.path.isfile(os.path.join(current, ".gitignore")):
                return current
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return None

    @staticmethod
    def _create_gitignore_matcher(gitignore_root: str) -> Any | None:
        """Lazily create a NestedGitignoreMatcher to avoid circular imports."""
        from app.domain.codebase.ignore import NestedGitignoreMatcher

        return NestedGitignoreMatcher(gitignore_root)

    @staticmethod
    def walk(root_path: str, options: TraverseOptions | None = None) -> Iterator[str]:
        """
        Standardized directory walker.
        Returns an iterator of full file paths.
        """
        options = options or TraverseOptions()
        exclude_dirs = options.exclude_dirs or DEFAULT_EXCLUDED_DIRS
        root_path = os.path.abspath(root_path)
        base_depth = root_path.rstrip(os.sep).count(os.sep)

        gitignore_root = FileTraverser._resolve_gitignore_root(root_path, options.gitignore_root)
        gitignore_matcher = None
        if gitignore_root:
            gitignore_matcher = FileTraverser._create_gitignore_matcher(gitignore_root)

        for root, dirs, files in os.walk(root_path):
            current_depth = root.rstrip(os.sep).count(os.sep) - base_depth

            # Depth control
            if options.max_depth is not None and current_depth >= options.max_depth:
                dirs[:] = []

            # Pruning ignored directories
            valid_dirs = []
            for d in dirs:
                d_path = os.path.join(root, d)
                if options.follow_ignore:
                    if d in exclude_dirs or is_ignored_path(d):
                        continue
                    if gitignore_matcher and gitignore_matcher.should_ignore(d_path, is_dir=True):
                        continue
                if options.dir_filter:
                    if not options.dir_filter(d_path):
                        continue
                valid_dirs.append(d)
            dirs[:] = valid_dirs

            # Yield directories if requested
            if options.include_dirs and root != root_path:
                yield root

            # Yield files
            for f in files:
                if options.follow_ignore and is_ignored_path(f):
                    continue

                full_path = os.path.join(root, f)
                if gitignore_matcher and gitignore_matcher.should_ignore(full_path, is_dir=False):
                    continue
                if options.filter_func:
                    if options.filter_func(full_path):
                        yield full_path
                else:
                    yield full_path

            if not options.recursive:
                break

    @staticmethod
    def list_entries(
        path: str,
        exclude_dirs: list[str] | None = None,
        follow_ignore: bool = True,
        gitignore_root: str | None = None,
    ) -> Iterator[os.DirEntry]:
        """
        Low-level shallow listing using os.scandir.
        Used for UI file explorers and lazy-loading.
        """
        exclude_dirs = exclude_dirs or DEFAULT_EXCLUDED_DIRS
        path = os.path.abspath(path)
        gitignore_root = FileTraverser._resolve_gitignore_root(path, gitignore_root)
        gitignore_matcher = None
        if gitignore_root:
            gitignore_matcher = FileTraverser._create_gitignore_matcher(gitignore_root)
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if follow_ignore:
                        if is_ignored_path(entry.name):
                            continue
                        if entry.is_dir() and entry.name in exclude_dirs:
                            continue
                        if gitignore_matcher and gitignore_matcher.should_ignore(entry.path, is_dir=entry.is_dir()):
                            continue
                    yield entry
        except (PermissionError, OSError) as e:
            logger.warning(f"Failed to list directory {path}: {e}", exc_info=True)
