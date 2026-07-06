import logging
import os
from typing import Any, Dict, List

from .traverser import FileTraverser

logger = logging.getLogger(__name__)

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
        exclude_dirs: List[str] | None = None
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
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug("Suppressed error: %s", e, exc_info=True)
        return nodes

    @staticmethod
    def get_text_tree(
        path: str,
        max_depth: int = 3,
        max_entries: int = 200,
        prefix: str = "",
        exclude_dirs: List[str] | None = None,
        _state: Dict | None = None,
        with_stats: bool = False,
    ) -> str:
        """
        Generate a compact text representation of the directory.
        Used for Agent context and documentation.
        """
        if _state is None:
            _state = {"count": 0, "truncated": False}

        # Helpers for stats
        def _format_size(size: int) -> str:
            if size < 1024: return f"{size}B"
            elif size < 1024 * 1024: return f"{size / 1024:.1f}K"
            elif size < 1024 * 1024 * 1024: return f"{size / (1024 * 1024):.1f}M"
            else: return f"{size / (1024 * 1024 * 1024):.1f}G"

        def _get_line_count(file_path: str, max_size: int = 1024 * 1024) -> int | None:
            try:
                size = os.path.getsize(file_path)
                if size == 0 or size > max_size: return None
                with open(file_path, "rb") as f:
                    if b"\x00" in f.read(4096): return None
                with open(file_path, "rb") as f:
                    return sum(1 for _ in f)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)
                return None

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
                        entry.path, max_depth - 1, max_entries, child_prefix, exclude_dirs, _state, with_stats
                    )
                    result.extend(subtree.split("\n")[1:]) # Skip child root as we prefix it
                    result[-(len(subtree.split("\n"))-1)] = f"{child_prefix}{entry.name}/"
                else:
                    stat_str = ""
                    if with_stats:
                        try:
                            st = entry.stat()
                            size_str = f"  {_format_size(st.st_size)}"
                            lines_str = ""
                            if st.st_size <= 1024 * 1024:
                                lc = _get_line_count(entry.path)
                                if lc is not None:
                                    lines_str = f" ({lc} lines)"
                            stat_str = f"{size_str}{lines_str}"
                        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                            logger.debug("Suppressed error: %s", e, exc_info=True)
                    result.append(f"{child_prefix}{entry.name}{stat_str}")
                    _state["count"] += 1
                    
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            result.append(f"{prefix}  [Error: {e}]")

        return "\n".join(result)
