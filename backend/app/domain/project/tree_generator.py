import fnmatch
import os
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.infrastructure.database.sql.database import session_scope
from app.models import CodeChunk, SourceFile


@dataclass
class TreeNode:
    name: str
    type: str  # 'dir', 'file', 'class', 'function', 'method'
    children: list["TreeNode"] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

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
        self.db_files_map = {}

    async def generate(self, style: str = "auto") -> str:
        """
        Generate the tree string.
        Args:
             style: 'tree' (ASCII art) or 'flat' (List of paths). 'auto' defaults to 'flat' if no symbols, 'tree' if symbols.
        """
        # 1. Fetch DB Data (Only if symbols requested)
        if self.with_symbols:
            async with session_scope() as session:
                self.db_files_map = await self._fetch_source_files_map(session)

        # 2. Build Tree Structure
        root_node = self._build_tree_structure()

        # 3. Determine Format
        if style == "auto":
            style = "tree" if self.with_symbols else "flat"

        if style == "flat":
            return self._render_flat(root_node)

        # 3. Adapt & Render (Tree)

        # Strategy: Try full detail -> No Methods -> No Classes -> Depth Limit

        # Level 1: Full Detail
        render = self._render_node(root_node, include_classes=True, include_methods=True)
        if self._is_within_limit(render):
            return render

        # Level 2: No Methods
        render = self._render_node(root_node, include_classes=True, include_methods=False)
        if self._is_within_limit(render):
            return render + "\n(Methods hidden due to size)"

        # Level 3: No Classes (Files only)
        render = self._render_node(root_node, include_classes=False, include_methods=False)
        if self._is_within_limit(render):
            return render + "\n(Symbols hidden due to size)"

        # Level 4: Truncated Files (enforce max_lines during rendering)
        render = self._render_node(root_node, include_classes=False, include_methods=False)
        return self._truncate_lines(render) + "\n(Tree truncated due to size. Use 'get_workspace_tree' with deeper filters to see more.)"

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

    def _build_tree_structure(self) -> TreeNode:
        from app.core.file.service import walk_tree
        from app.domain.codebase.filter import FileFilter

        self.file_filter = FileFilter()

        root_node = TreeNode(os.path.basename(self.root_path), "dir")

        # Map: abs_path -> TreeNode (for efficient retrieval during reconstruction)
        nodes_map = {self.root_path: root_node}

        for full_path in walk_tree(self.root_path, filter_func=self.file_filter.should_include, max_depth=self.max_depth):

            # Pattern Filter (fnmatch)
            filename = os.path.basename(full_path)
            if self.pattern and not fnmatch.fnmatch(filename, self.pattern):
                continue

            # Build Tree Path
            rel_path = os.path.relpath(full_path, self.root_path)
            parts = rel_path.split(os.sep)

            # Start from root and traverse/create
            current_node = root_node
            current_abs = self.root_path

            for i, part in enumerate(parts):
                is_last_part = (i == len(parts) - 1)
                current_abs = os.path.join(current_abs, part)

                if current_abs in nodes_map:
                    current_node = nodes_map[current_abs]
                else:
                    # Create new node
                    node_type = "file" if is_last_part else "dir"
                    new_node = TreeNode(part, node_type)
                    current_node.add_child(new_node)
                    nodes_map[current_abs] = new_node
                    current_node = new_node

            # At end of loop, current_node is the file node
            file_node = current_node

            # Add Symbols
            chunks = []
            if rel_path in self.db_files_map:
                chunks = self.db_files_map[rel_path]

            self._add_symbols_to_file_node(file_node, chunks)

        # Post-process: Prune empty directories if pattern is active
        # Or always? walk_tree only yields files. Dirs only exist if they lead to valid files.
        # So "empty dirs" that contain no code files shouldn't logically exist in this constructed tree.
        # Exception: Dirs created by one file that was later skipped? No.
        # Wait, if pattern skipped the file, the dir node wasn't created.
        # BUT: Explicitly strictly empty dirs (no files at all deep down) are auto-pruned by this logic.
        # This is strictly better than _prune_empty_dirs!
        # However, _prune_empty_dirs might still be needed if `pattern` is applied in the loop?
        # If all files in a dir match pattern "exclude", then we skip them. We never create the dir node.
        # So _prune_empty_dirs is implicit!
        # Unless we want to keep dirs that match pattern? But pattern usually applies to files.

        # Let's keep `_prune_empty_dirs` call just in case I missed an edge case or for legacy safety?
        # Actually logic says: if file is skipped, loops continues. dir nodes not created.
        # So structure is clean by definition.

        if self.pattern:
            self._prune_empty_dirs(root_node)

        root_node.sort_children()
        return root_node

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
                c_node = TreeNode(name, "class")
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
                    f_node = TreeNode(name, "function")
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
                            m_node = TreeNode(method_name, "method")
                            classes[parent_id].add_child(m_node)
                            continue

        # 3. Add Top Level Functions
        for fn in functions:
            file_node.add_child(fn)

    def _render_node(
        self,
        node: TreeNode,
        include_classes: bool = True,
        include_methods: bool = True,
        prefix: str = "",
        is_last: bool = True,
        is_root: bool = True,
    ) -> str:
        lines = []

        # Render Info
        connector = ""
        if not is_root:
            connector = "└── " if is_last else "├── "

        icon = ""
        suffix = ""
        if node.type == "dir":
            suffix = "/"
        elif node.type == "class":
            icon = "[C] "
        elif node.type == "function":
            icon = "[F] "
        elif node.type == "method":
            icon = "[m] "

        display_name = f"{prefix}{connector}{icon}{node.name}{suffix}"

        # Filter Logic
        if node.type == "class" and not include_classes:
            return ""
        if node.type == "method" and not include_methods:
            return ""
        if node.type == "function" and not include_methods:  # Treat top-level functions like methods for simplicity of "details"
            return ""

        if not is_root:
            lines.append(display_name)
        else:
            if self.include_root:
                lines.append(f"{node.name}/")

        # Children Sort & Filter
        visible_children = list(node.children)

        # Prepare prefix for children
        if is_root:
            child_prefix = ""
        else:
            child_prefix = prefix + ("    " if is_last else "│   ")

        count = len(visible_children)
        for i, child in enumerate(visible_children):
            is_last_child = i == count - 1
            child_text = self._render_node(
                child,
                include_classes,
                include_methods,
                child_prefix,
                is_last_child,
                is_root=False,
            )
            if child_text:
                lines.append(child_text)

        return "\n".join(lines)

    def _render_flat(self, node: TreeNode, prefix: str = None) -> str:
        """
        Recursive flat list renderer.
        Returns accumulated paths relative to root.
        """
        lines = []

        # Calculate current path
        if prefix is None:
            # Root Node
            current_path = node.name if self.include_root else ""
        else:
            current_path = os.path.join(prefix, node.name) if prefix else node.name

        # Add self if file
        if node.type == "file":
            # Only add if path is not empty
            if current_path:
                lines.append(current_path)

        # Recurse
        files_shown = 0
        total_files = len([c for c in node.children if c.type == "file"])

        for child in node.children:
            if child.type == "dir":
                child_lines = self._render_flat(child, prefix=current_path)
                if child_lines:
                    lines.append(child_lines)

            elif child.type == "file":
                if files_shown < self.file_limit:
                    # Render File
                    # Use current_path (parent) to construct child path
                    child_path = os.path.join(current_path, child.name) if current_path else child.name
                    lines.append(child_path)
                    files_shown += 1
                else:
                    # Limit Reached
                    remaining = total_files - files_shown
                    lines.append(f"{current_path}/... (+ {remaining} more files)")
                    break

        return "\n".join(lines)

    async def _fetch_source_files_map(self, session) -> dict[str, list[CodeChunk]]:
        # Modified to fetch chunks with identifiers
        stmt = select(SourceFile).options(selectinload(SourceFile.chunks))
        result = await session.execute(stmt)
        files = result.scalars().all()

        mapping = {}
        for sf in files:
            mapping[sf.path] = sf.chunks
        return mapping

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
