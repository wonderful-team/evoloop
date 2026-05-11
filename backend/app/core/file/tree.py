import os
from typing import List, Dict, Optional, Any
from .traverser import FileTraverser, TraverseOptions
from .filter import is_ignored_path

class TreeService:
    """
    Unified service for generating hierarchical file structures.
    Supports JSON (for UI) and Text (for Agent/Docs).
    """

    @staticmethod
    def get_json_tree(
        root_path: str,
        rel_path: str = "",
        max_depth: int = 1, # Default shallow for UI
        exclude_dirs: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate a JSON structure for UI file explorers.
        Supports lazy loading by controlling depth.
        """
        nodes = []
        target_dir = os.path.join(root_path, rel_path) if rel_path else root_path
        
        try:
            entries = sorted(
                FileTraverser.list_entries(target_dir, exclude_dirs),
                key=lambda e: (not e.is_dir(), e.name.lower())
            )
            for entry in entries:
                node_rel_path = os.path.join(rel_path, entry.name)
                node = {
                    "name": entry.name,
                    "path": node_rel_path,
                    "type": "directory" if entry.is_dir() else "file"
                }
                
                # If depth allows, recurse (though usually UI uses lazy loading)
                if entry.is_dir() and max_depth > 1:
                    node["children"] = TreeService.get_json_tree(
                        root_path, node_rel_path, max_depth - 1, exclude_dirs
                    )
                
                nodes.append(node)
        except Exception:
            pass
        return nodes

    @staticmethod
    def get_text_tree(
        path: str,
        max_depth: int = 3,
        max_entries: int = 200,
        prefix: str = "",
        exclude_dirs: Optional[List[str]] = None,
        _state: Optional[Dict] = None
    ) -> str:
        """
        Generate a compact text representation of the directory.
        Used for Agent context and documentation.
        """
        if _state is None:
            _state = {"count": 0, "truncated": False}

        if not os.path.isdir(path):
            return f"Not a directory: {path}"

        result = []
        base_name = os.path.basename(path) or path
        
        if prefix:
            result.append(f"{prefix}{base_name}/")
        else:
            result.append(f"{base_name}/")
        
        _state["count"] += 1
        
        if max_depth <= 0 or _state["count"] >= max_entries:
            return "\n".join(result)

        try:
            entries = sorted(
                FileTraverser.list_entries(path, exclude_dirs),
                key=lambda e: (not e.is_dir(), e.name.lower())
            )
            
            for entry in entries:
                if _state["count"] >= max_entries:
                    result.append(f"{prefix}  ... (more entries hidden)")
                    _state["truncated"] = True
                    break
                
                child_prefix = f"{prefix}  "
                if entry.is_dir():
                    subtree = TreeService.get_text_tree(
                        entry.path, max_depth - 1, max_entries, child_prefix, exclude_dirs, _state
                    )
                    result.extend(subtree.split("\n")[1:]) # Skip child root as we prefix it
                    result[-(len(subtree.split("\n"))-1)] = f"{child_prefix}{entry.name}/"
                else:
                    result.append(f"{child_prefix}{entry.name}")
                    _state["count"] += 1
                    
        except Exception as e:
            result.append(f"{prefix}  [Error: {e}]")

        return "\n".join(result)
