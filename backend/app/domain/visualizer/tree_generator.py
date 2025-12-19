import os
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.config import settings
from app.infrastructure.database.sql.database import get_db
from app.infrastructure.database.sql.models import SourceFile, CodeChunk


@dataclass
class TreeNode:
    name: str
    type: str  # 'dir', 'file', 'class', 'function', 'method'
    children: List['TreeNode'] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def add_child(self, node: 'TreeNode'):
        self.children.append(node)

    def sort_children(self):
        # Sort directories first, then files, then others
        # Within same type, alpha sort
        def sort_key(n):
            type_score = 0
            if n.type == 'dir':
                type_score = 1
            elif n.type == 'file':
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

    def __init__(self, root_path: str, max_lines: int = None):
        self.root_path = os.path.abspath(root_path)
        self.max_lines = max_lines or settings.TREE_VIEW_MAX_LINES
        self.db_files_map = {}

    async def generate(self) -> str:
        # 1. Fetch DB Data
        async with get_db() as session:
            self.db_files_map = await self._fetch_source_files_map(session)

        # 2. Build Tree Structure
        root_node = self._build_tree_structure()

        # 3. Adapt & Render
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

        # Level 4: Truncated Files (handled by max_lines in loop usually, but here we can enforce depth)
        # For now, just return the truncated Level 3
        return self._truncate_lines(render)

    def _is_within_limit(self, text: str) -> bool:
        return text.count('\n') <= self.max_lines

    def _truncate_lines(self, text: str) -> str:
        lines = text.split('\n')
        if len(lines) > self.max_lines:
            return '\n'.join(lines[:self.max_lines]) + f"\n... [Truncated at {self.max_lines} lines]"
        return text

    def _build_tree_structure(self) -> TreeNode:
        root_node = TreeNode(os.path.basename(self.root_path), 'dir')

        # os.walk yields (dirpath, dirnames, filenames)
        # We need to map paths to nodes to build hierarchy
        # Since os.walk is top-down, parent should exist (mostly)

        # Actually, building a tree from os.walk is tricky if we want a single root object.
        # Let's use a path map.
        nodes_map = {self.root_path: root_node}

        for root, dirs, files in os.walk(self.root_path):
            # Exclude filters
            dirs[:] = [d for d in dirs if
                       d not in {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.idea', '.vscode'}]

            current_node = nodes_map.get(root)
            if not current_node:
                # Should not happen if we traverse top-down and initialize root
                continue

            # Add Directories
            for d in dirs:
                d_abs = os.path.join(root, d)
                d_node = TreeNode(d, 'dir')
                current_node.add_child(d_node)
                nodes_map[d_abs] = d_node

            # Add Files
            for f in files:
                f_abs = os.path.join(root, f)
                f_node = TreeNode(f, 'file')
                current_node.add_child(f_node)

                # Add Symbols to File
                rel_path = os.path.relpath(f_abs, self.root_path)
                chunks = self.db_files_map.get(rel_path, [])
                self._add_symbols_to_file_node(f_node, chunks)

        root_node.sort_children()
        return root_node

    def _add_symbols_to_file_node(self, file_node: TreeNode, chunks: List[CodeChunk]):
        if not chunks:
            return

        # Group by Class
        classes = {}  # identifier -> Node
        functions = []  # Nodes

        # 1. Create Class Nodes & Collect Top-level Functions
        for chunk in chunks:
            if chunk.chunk_type == 'class':
                # Simplified: use last part of identifier as name
                name = chunk.identifier.split('.')[-1]
                c_node = TreeNode(name, 'class')
                classes[chunk.identifier] = c_node
                file_node.add_child(c_node)
            elif chunk.chunk_type == 'function':
                # Check if it belongs to a class? 
                # In current DB model, identifiers might be "ClassName.method".
                # If chunk_type is function, and identifier has '.', it could be a method.
                if '.' in chunk.identifier and not chunk.identifier.startswith('.'):
                    # Likely a method
                    pass
                else:
                    # Top level function
                    name = chunk.identifier.split('.')[-1]
                    f_node = TreeNode(name, 'function')
                    functions.append(f_node)

        # 2. Distribute Methods (Chunk type might be 'function' or specific 'method' depending on indexer)
        # Assuming indexer marks methods as 'function' or 'method' but identifier has 'Class.method'
        for chunk in chunks:
            if chunk.chunk_type in ('function', 'method'):
                if '.' in chunk.identifier:
                    parts = chunk.identifier.split('.')
                    # Heuristic: If we have a class matching the prefix, attach it
                    # Try possible parent identifiers
                    # e.g. A.B.method -> try A.B, then A
                    # For simple A.method:
                    if len(parts) >= 2:
                        parent_id = '.'.join(parts[:-1])
                        method_name = parts[-1]

                        if parent_id in classes:
                            m_node = TreeNode(method_name, 'method')
                            classes[parent_id].add_child(m_node)
                            continue

        # 3. Add Top Level Functions
        for fn in functions:
            file_node.add_child(fn)

    def _render_node(self, node: TreeNode, include_classes: bool = True, include_methods: bool = True, prefix: str = "",
                     is_last: bool = True, is_root: bool = True) -> str:
        lines = []

        # Render Info
        connector = ""
        if not is_root:
            connector = "└── " if is_last else "├── "

        icon = ""
        if node.type == 'dir':
            icon = "/"
        elif node.type == 'class':
            icon = "[C] "
        elif node.type == 'function':
            icon = "[F] "
        elif node.type == 'method':
            icon = "[m] "

        display_name = f"{prefix}{connector}{icon}{node.name}"

        # Filter Logic
        if node.type == 'class' and not include_classes:
            return ""
        if node.type == 'method' and not include_methods:
            return ""
        if node.type == 'function' and not include_methods:  # Treat top-level functions like methods for simplicity of "details"
            return ""

        if not is_root:  # Root name is usually handled by caller or just printed
            lines.append(display_name)
        else:
            lines.append(f"{node.name}/")

        # Children Sort & Filter
        visible_children = [c for c in node.children]

        # Prepare prefix for children
        if is_root:
            child_prefix = ""
        else:
            child_prefix = prefix + ("    " if is_last else "│   ")

        count = len(visible_children)
        for i, child in enumerate(visible_children):
            is_last_child = (i == count - 1)
            child_text = self._render_node(child, include_classes, include_methods, child_prefix, is_last_child,
                                           is_root=False)
            if child_text:
                lines.append(child_text)

        return "\n".join(lines)

    async def _fetch_source_files_map(self, session) -> Dict[str, List[CodeChunk]]:
        # Modified to fetch chunks with identifiers
        stmt = select(SourceFile).options(selectinload(SourceFile.chunks))
        result = await session.execute(stmt)
        files = result.scalars().all()

        mapping = {}
        for sf in files:
            mapping[sf.path] = sf.chunks
        return mapping
