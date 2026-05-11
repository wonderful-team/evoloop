import os
import logging
from typing import Iterator, List, Optional, Callable
from dataclasses import dataclass

from app.constants import DEFAULT_EXCLUDED_DIRS
from .filter import is_ignored_path

logger = logging.getLogger(__name__)

@dataclass
class TraverseOptions:
    """Configuration for directory traversal."""
    max_depth: Optional[int] = None
    exclude_dirs: Optional[List[str]] = None
    filter_func: Optional[Callable[[str], bool]] = None
    include_dirs: bool = False
    recursive: bool = True
    follow_ignore: bool = True

class FileTraverser:
    """
    Unified, high-performance file system traverser.
    Single source of truth for all directory walking and listing.
    """
    
    @staticmethod
    def walk(
        root_path: str,
        options: Optional[TraverseOptions] = None
    ) -> Iterator[str]:
        """
        Standardized directory walker.
        Returns an iterator of full file paths.
        """
        options = options or TraverseOptions()
        exclude_dirs = options.exclude_dirs or DEFAULT_EXCLUDED_DIRS
        root_path = os.path.abspath(root_path)
        base_depth = root_path.rstrip(os.sep).count(os.sep)

        for root, dirs, files in os.walk(root_path):
            current_depth = root.rstrip(os.sep).count(os.sep) - base_depth

            # Depth control
            if options.max_depth is not None and current_depth >= options.max_depth:
                dirs[:] = []

            # Pruning ignored directories
            if options.follow_ignore:
                valid_dirs = []
                for d in dirs:
                    if d in exclude_dirs or is_ignored_path(d):
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
        exclude_dirs: Optional[List[str]] = None,
        follow_ignore: bool = True
    ) -> Iterator[os.DirEntry]:
        """
        Low-level shallow listing using os.scandir.
        Used for UI file explorers and lazy-loading.
        """
        exclude_dirs = exclude_dirs or DEFAULT_EXCLUDED_DIRS
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if follow_ignore:
                        if is_ignored_path(entry.name):
                            continue
                        if entry.is_dir() and entry.name in exclude_dirs:
                            continue
                    yield entry
        except (PermissionError, OSError) as e:
            logger.warning(f"Failed to list directory {path}: {e}")
