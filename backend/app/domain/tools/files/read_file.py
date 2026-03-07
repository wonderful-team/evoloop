import re
from typing import Annotated
from langchain_core.tools import InjectedToolArg
from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool

from .actions.read import handle_read


@evoloop_tool(is_pollable=True)
async def read_file(
    path: str | None = None,
    start_line: str | int | None = None,
    end_line: str | int | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Read the contents of a file.

    Args:
        path: Absolute or relative path to the file. **REQUIRED**
        start_line: Optional start line (1-indexed). Can be int or string.
        end_line: Optional end line (1-indexed, inclusive). Can be int or string.
    """
    if not path:
        return "Error: Missing argument 'path'. usage: read_file(path='...')"

    # Helper to safely parse integers from loose model output (e.g. "1 Union College")
    def safe_int(val):
        if val is None:
            return None
        if isinstance(val, int):
            return val
        try:
            # Try simple conversion
            return int(str(val).strip())
        except ValueError:
            # Fallback: Extract first digit sequence if mixed garbage
            match = re.search(r"\d+", str(val))
            if match:
                return int(match.group())
            return None

    s = safe_int(start_line)
    e = safe_int(end_line)

    return await handle_read(path, s, e, config=config)
