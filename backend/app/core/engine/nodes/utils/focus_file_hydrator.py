"""
Focus file hydrator — retrieves file contents for Worker prompts.
"""

import logging
import os

from app.core.engine.prompts.utils import get_mapped_cwd
from app.core.engine.state.config import ExecutionTicket

logger = logging.getLogger(__name__)


class FocusFileHydrator:
    """Retrieve focus-file data as structured objects."""

    @staticmethod
    async def hydrate(ticket: ExecutionTicket | None, ctx) -> list[dict]:
        """
        Retrieve focus-file data as structured objects.
        Returns a list of dicts with keys: rel_path, status, content/detail.
        """
        if not ticket:
            return []
        focus_paths = ticket.focus_paths or []
        if not focus_paths:
            return []

        cwd = ctx.working_directory or ""
        results = []

        for path_item in focus_paths:
            try:
                # 1. Path Normalization & Integration (Handle absolute host paths from Supervisor)
                if os.path.isabs(path_item):
                    full_path = path_item
                    display_path = get_mapped_cwd(path_item)
                else:
                    full_path = os.path.join(cwd, path_item) if cwd else path_item
                    display_path = path_item

                if not os.path.exists(full_path):
                    results.append({"rel_path": display_path, "status": "missing"})
                    continue

                if os.path.isdir(full_path):
                    results.append({
                        "rel_path": display_path,
                        "status": "directory",
                        "detail": "This is a directory. Use 'list_dir(tree=True)' to examine."
                    })
                    continue

                size = os.path.getsize(full_path)
                if size > 30_000:
                    results.append({"rel_path": display_path, "status": "skipped", "detail": f"Too large: {size}b"})
                    continue

                with open(full_path, encoding="utf-8") as f:
                    file_content = f.read()
                results.append({"rel_path": display_path, "status": "ok", "content": file_content})
            except OSError as e:
                results.append({"rel_path": path_item, "status": "error", "detail": str(e)})

        return results
