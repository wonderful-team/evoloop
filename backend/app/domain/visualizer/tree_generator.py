import os
from dataclasses import dataclass, field
from typing import List, Dict

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.infrastructure.database.sql.database import session_scope
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

    def __init__(self, root_path: str, max_lines: int = None, max_depth: int = 3, include_root: bool = False, pattern: str = None):
        self.root_path = os.path.abspath(root_path)
        self.max_lines = max_lines or settings.TREE_VIEW_MAX_LINES
        self.max_depth = max_depth
        self.include_root = include_root
        self.pattern = pattern
        self.db_files_map = {}

    async def generate(self) -> str:
        # 1. Fetch DB Data
        async with session_scope() as session:
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
        
        from app.domain.codebase.filter import FileFilter
        from app.constants import BLACKLIST_DIRS
        
        self.file_filter = FileFilter()
        
        root_node = TreeNode(os.path.basename(self.root_path), 'dir')
        nodes_map = {self.root_path: root_node}

    def __init__(self, root_path: str, max_lines: int = None, max_depth: int = 3, include_root: bool = False, pattern: str = None):
        self.root_path = os.path.abspath(root_path)
        self.max_lines = max_lines or settings.TREE_VIEW_MAX_LINES
        self.max_depth = max_depth
        self.include_root = include_root
        self.pattern = pattern
        self.db_files_map = {}

    def _build_tree_structure(self) -> TreeNode:
        
        from app.domain.codebase.filter import FileFilter
        from app.constants import BLACKLIST_DIRS
        import fnmatch
        
        self.file_filter = FileFilter()
        
        root_node = TreeNode(os.path.basename(self.root_path), 'dir')
        nodes_map = {self.root_path: root_node}

        for root, dirs, files in os.walk(self.root_path):
            # Calculate current depth relative to self.root_path
            # Root path itself is depth 0.
            # rel_path will be empty at root, "subdir" at depth 1.
            rel_root = os.path.relpath(root, self.root_path)
            if rel_root == ".":
                current_depth = 0
            else:
                current_depth = len(rel_root.split(os.sep))
            
            # Prune if too deep
            # If we are AT max_depth, we process files, but prune dirs so we don't go deeper.
            # If we are ABOVE max_depth (shouldn't happen with prune), continue.
            if current_depth >= self.max_depth:
                dirs[:] = []
                # continue # If we continue, we skip files at this level too.
                # Decision: Show files at max depth, but no subdirs.
                # So we let execution proceed to process 'files', but cleared 'dirs' stops recursion.
            
            # Exclude filters - Prune directories in-place (moved after depth check to save cycles)
            # 1. Basic Blacklist (Constants)
            # 2. Startswith .
            d_to_remove = []
            for d in dirs:
                if d in BLACKLIST_DIRS or d.startswith('.'):
                    d_to_remove.append(d)
                else:
                    # Check if file filter excludes this directory explicitly
                    full_d_path = os.path.join(root, d)
                    pass
            
            for d in d_to_remove:
                dirs.remove(d)

            current_node = nodes_map.get(root)
            if not current_node:
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
                
                # USE FILE FILTER
                if not self.file_filter.should_include(f_abs):
                    continue

                # PATTERN FILTER
                if self.pattern and not fnmatch.fnmatch(f, self.pattern):
                    continue
                    
                f_node = TreeNode(f, 'file')
                current_node.add_child(f_node)

                # Add Symbols to File
                rel_path = os.path.relpath(f_abs, self.root_path)
                chunks = self.db_files_map.get(rel_path, [])
                self._add_symbols_to_file_node(f_node, chunks)

        # Post-process: Prune empty directories if pattern is active
        if self.pattern:
            self._prune_empty_dirs(root_node)
            
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
        suffix = ""
        if node.type == 'dir':
            suffix = "/"
        elif node.type == 'class':
            icon = "[C] "
        elif node.type == 'function':
            icon = "[F] "
        elif node.type == 'method':
            icon = "[m] "

        display_name = f"{prefix}{connector}{icon}{node.name}{suffix}"

        # Filter Logic
        if node.type == 'class' and not include_classes:
            return ""
        if node.type == 'method' and not include_methods:
            return ""
        if node.type == 'function' and not include_methods:  # Treat top-level functions like methods for simplicity of "details"
            return ""

        if not is_root:
            lines.append(display_name)
        else:
            if self.include_root:
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

    def _prune_empty_dirs(self, node: TreeNode) -> bool:
        """
        Recursively prune directories that contain no files (or only empty directories).
        Returns True if node should be kept, False if it should be removed.
        """
        if node.type != 'dir':
            return True

        # Prune children first
        node.children = [c for c in node.children if self._prune_empty_dirs(c)]

        # Keep if it has children, OR if it's the root (we usually keep root)
        # But if root is strictly empty after filter, maybe we keep it to show "No results"?
        # Let's say we remove it if empty, but caller handles root.
        return len(node.children) > 0
