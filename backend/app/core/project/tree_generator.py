import fnmatch
import logging
import os

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.project import cache as project_cache
from app.infrastructure.database import session_scope
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models import CodeChunk, Repository, SourceFile
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class TreeNode(DynamicBaseModel):
    name: str
    type: str  # 'dir', 'file', 'class', 'function', 'method'
    children: list["TreeNode"] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def add_child(self, node: "TreeNode"):
        self.children.append(node)

    def sort_children(self):
        # Sort directories first, then files, then others
        # Within same type, alpha sort
        def sort_key(n):
            type_score = 0
            if n.type == "dir":
                type_score = 1
            elif n.type == "file":
                type_score = 2
            else:
                type_score = 3
            return (type_score, n.name.lower())

        self.children.sort(key=sort_key)
        for child in self.children:
            child.sort_children()


class AnnotatedTreeGenerator:
    """
    Generates a directory tree annotated with indexed code symbols.
    Features:
    - Nested display: File -> Class -> Method
    - Adaptive detail: Auto-hides methods/classes if tree is too large
    - ASCII formatting
    """

    def __init__(
        self,
        root_path: str,
        max_lines: int = None,
        max_depth: int = 3,
        include_root: bool = False,
        pattern: str = None,
        with_symbols: bool = True,
        file_limit: int = 50,
    ):
        self.root_path = os.path.abspath(root_path)
        self.max_lines = max_lines or settings.TREE_VIEW_MAX_LINES
        self.max_depth = max_depth
        self.include_root = include_root
        self.pattern = pattern
        self.with_symbols = with_symbols
        self.file_limit = file_limit

    async def generate(self, style: str = "auto") -> str:
        """
        Generate the tree string.
        Args:
             style: 'tree' (ASCII art) or 'flat' (List of paths). 'auto' defaults to 'tree'.
        """
        root_node = await self._build_tree_structure()

        if style == "auto":
            style = "tree"

        try:
            if style == "flat":
                flat_paths = self._collect_flat_paths(root_node)
                return render_template("domain/codebase/codebase_tree.prompt.j2", style="flat", flat_paths=flat_paths)

            return render_template("domain/codebase/codebase_tree.prompt.j2", style="tree", root=root_node)
        except Exception as e:
            logger.error(f"Failed to render tree: {e}")
            return "Error rendering tree structure."

    def _collect_flat_paths(self, node: TreeNode, prefix: str = "") -> list[str]:
        paths = []
        current_path = os.path.join(prefix, node.name) if prefix else node.name
        if node.type == "file":
            paths.append(current_path)

        for child in node.children:
            if child.type == "dir":
                paths.extend(self._collect_flat_paths(child, current_path))
            elif child.type == "file":
                paths.append(os.path.join(current_path, child.name))
        return paths

    def _is_within_limit(self, text: str) -> bool:
        if not self.max_lines:
            return True
        return text.count("\n") <= self.max_lines

    def _truncate_lines(self, text: str) -> str:
        if not self.max_lines:
            return text
        lines = text.split("\n")
        if len(lines) > self.max_lines:
            return "\n".join(lines[: self.max_lines]) + f"\n... [Truncated at {self.max_lines} lines]"
        return text

    def _is_path_ignored(self, path: str, ignored_paths: set) -> bool:
        """
        Check if a path should be ignored based on the ignored project paths.

        Args:
            path: The path to check
            ignored_paths: Set of ignored project paths

        Returns:
            True if the path should be ignored
        """
        abs_path = os.path.abspath(path)

        for ignored_path in ignored_paths:
            # Check if path is exactly the ignored path
            if abs_path == ignored_path:
                return True
            # Check if path is inside an ignored project
            # Use os.sep to ensure we're matching directory boundaries
            if abs_path.startswith(ignored_path + os.sep):
                return True

        return False

    def _add_symbols_to_file_node(self, file_node: TreeNode, chunks: list[CodeChunk]):
        if not chunks:
            return

        # Group by Class
        classes = {}  # identifier -> Node
        functions = []  # Nodes

        # 1. Create Class Nodes & Collect Top-level Functions
        for chunk in chunks:
            if chunk.chunk_type == "class":
                # Simplified: use last part of identifier as name
                name = chunk.identifier.split(".")[-1]
                c_node = TreeNode(name=name, type="class")
                classes[chunk.identifier] = c_node
                file_node.add_child(c_node)
            elif chunk.chunk_type == "function":
                # Check if it belongs to a class?
                # In current DB model, identifiers might be "ClassName.method".
                # If chunk_type is function, and identifier has '.', it could be a method.
                if "." in chunk.identifier and not chunk.identifier.startswith("."):
                    # Likely a method
                    pass
                else:
                    # Top level function
                    name = chunk.identifier.split(".")[-1]
                    f_node = TreeNode(name=name, type="function")
                    functions.append(f_node)

        # 2. Distribute Methods (Chunk type might be 'function' or specific 'method' depending on indexer)
        # Assuming indexer marks methods as 'function' or 'method' but identifier has 'Class.method'
        for chunk in chunks:
            if chunk.chunk_type in ("function", "method"):
                if "." in chunk.identifier:
                    parts = chunk.identifier.split(".")
                    # Heuristic: If we have a class matching the prefix, attach it
                    # Try possible parent identifiers
                    # e.g. A.B.method -> try A.B, then A
                    # For simple A.method:
                    if len(parts) >= 2:
                        parent_id = ".".join(parts[:-1])
                        method_name = parts[-1]

                        if parent_id in classes:
                            m_node = TreeNode(name=method_name, type="method")
                            classes[parent_id].add_child(m_node)
                            continue

        # 3. Add Top Level Functions
        for fn in functions:
            file_node.add_child(fn)

    def _prune_empty_dirs(self, node: TreeNode) -> bool:
        """
        Recursively prune directories that contain no files (or only empty directories).
        Returns True if node should be kept, False if it should be removed.
        """
        if node.type != "dir":
            return True

        # Prune children first
        node.children = [c for c in node.children if self._prune_empty_dirs(c)]

        # Keep if it has children, OR if it's the root (we usually keep root)
        # But if root is strictly empty after filter, maybe we keep it to show "No results"?
        # Let's say we remove it if empty, but caller handles root.
        return len(node.children) > 0

    async def _build_tree_structure(self) -> TreeNode:
        from app.domain.codebase.filter import FileFilter

        self.file_filter = FileFilter()
        ignored_paths = await project_cache.get_ignored_paths()

        # Try DB assembly first (no disk access). Fallback to physical walk if
        # the project hasn't been indexed yet (scan_status != 'completed').
        db_root = await self._build_tree_from_db(ignored_paths)
        if db_root is not None:
            return db_root

        logger.info(
            f"[TreeGenerator] DB assembly not available for {self.root_path}, "
            "falling back to physical walk."
        )

        return await self._build_tree_from_disk(ignored_paths)

    async def _build_tree_from_db(self, ignored_paths: set) -> TreeNode | None:
        """Build the tree purely from SourceFile/CodeChunk in the DB."""

        async with session_scope() as session:
            repo = await self._find_repository_by_path(session, self.root_path)
            if repo is None or not repo.local_path:
                return None

            repo_path = repo.local_path
            stmt = select(SourceFile).where(
                SourceFile.repository_id == repo.id,
                SourceFile.scan_status == "completed",
            )
            if self.with_symbols:
                stmt = stmt.options(selectinload(SourceFile.chunks))
            result = await session.execute(stmt)
            source_files = result.scalars().all()
            if not source_files:
                return None

            root_node = TreeNode(name=os.path.basename(self.root_path), type="dir")
            nodes_map = {self.root_path: root_node}

            for sf in source_files:
                full_path = os.path.join(repo_path, sf.path)
                if not full_path.startswith(self.root_path):
                    continue
                if self._is_path_ignored(full_path, ignored_paths):
                    continue

                rel_path = os.path.relpath(full_path, self.root_path)
                parts = rel_path.split(os.sep)
                if len(parts) > self.max_depth:
                    continue

                filename = os.path.basename(full_path)
                if self.pattern and not fnmatch.fnmatch(filename, self.pattern):
                    continue
                if not self.file_filter.should_include(full_path):
                    continue

                current_node = root_node
                current_abs = self.root_path
                for i, part in enumerate(parts):
                    is_last_part = i == len(parts) - 1
                    current_abs = os.path.join(current_abs, part)
                    if current_abs in nodes_map:
                        current_node = nodes_map[current_abs]
                    else:
                        node_type = "file" if is_last_part else "dir"
                        new_node = TreeNode(name=part, type=node_type)
                        current_node.add_child(new_node)
                        nodes_map[current_abs] = new_node
                        current_node = new_node

                file_node = current_node
                if self.with_symbols:
                    self._add_symbols_to_file_node(file_node, sf.chunks)

            if self.pattern:
                self._prune_empty_dirs(root_node)
            root_node.sort_children()
            return root_node

    async def _find_repository_by_path(
        self, session, root_path: str
    ) -> Repository | None:
        """Find the repository whose local_path matches or contains root_path."""

        root_path = os.path.abspath(root_path)
        stmt = select(Repository).where(Repository.local_path == root_path)
        result = await session.execute(stmt)
        repo = result.scalar_one_or_none()
        if repo is not None:
            return repo

        stmt = select(Repository)
        result = await session.execute(stmt)
        for candidate in result.scalars().all():
            if candidate.local_path and root_path.startswith(
                candidate.local_path + os.sep
            ):
                return candidate
        return None

    async def _build_tree_from_disk(self, ignored_paths: set) -> TreeNode:
        from app.core.file.service import walk_tree

        if self._is_path_ignored(self.root_path, ignored_paths):
            logger.warning(
                f"[TreeGenerator] Root path is inside ignored project: {self.root_path}"
            )
            return TreeNode(name=os.path.basename(self.root_path), type="dir")

        db_files_map: dict[str, list[CodeChunk]] = {}
        if self.with_symbols:
            db_files_map = await self._fetch_source_files_map_for_disk()

        root_node = TreeNode(name=os.path.basename(self.root_path), type="dir")
        nodes_map = {self.root_path: root_node}

        def dir_filter(dir_path: str) -> bool:
            return not self._is_path_ignored(dir_path, ignored_paths)

        for full_path in walk_tree(
            self.root_path,
            filter_func=self.file_filter.should_include,
            max_depth=self.max_depth,
            dir_filter=dir_filter,
        ):
            filename = os.path.basename(full_path)
            if self.pattern and not fnmatch.fnmatch(filename, self.pattern):
                continue

            rel_path = os.path.relpath(full_path, self.root_path)
            parts = rel_path.split(os.sep)

            current_node = root_node
            current_abs = self.root_path
            for i, part in enumerate(parts):
                is_last_part = i == len(parts) - 1
                current_abs = os.path.join(current_abs, part)

                if current_abs in nodes_map:
                    current_node = nodes_map[current_abs]
                else:
                    node_type = "file" if is_last_part else "dir"
                    new_node = TreeNode(name=part, type=node_type)
                    current_node.add_child(new_node)
                    nodes_map[current_abs] = new_node
                    current_node = new_node

            file_node = current_node
            chunks = db_files_map.get(rel_path, [])
            self._add_symbols_to_file_node(file_node, chunks)

        if self.pattern:
            self._prune_empty_dirs(root_node)

        root_node.sort_children()
        return root_node

    async def _fetch_source_files_map_for_disk(self) -> dict[str, list[CodeChunk]]:
        async with session_scope() as session:
            repo = await self._find_repository_by_path(session, self.root_path)
            if repo is None or not repo.local_path:
                return {}

            repo_path = repo.local_path

            stmt = (
                select(SourceFile)
                .where(SourceFile.repository_id == repo.id)
                .options(selectinload(SourceFile.chunks))
            )
            result = await session.execute(stmt)
            files = result.scalars().all()

            mapping = {}
            for sf in files:
                full_path = os.path.join(repo_path, sf.path)
                rel_path = os.path.relpath(full_path, self.root_path)
                mapping[rel_path] = sf.chunks
            return mapping
