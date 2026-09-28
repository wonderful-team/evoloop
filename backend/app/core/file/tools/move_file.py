import os
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.file import move_path
from app.core.tools.base import InjectedToolArg

from .utils import resolve_and_validate_path


async def move_file(
    source: str,
    destination: str,
    overwrite: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    Move or rename a file or directory.

    Args:
        source: The current path of the file or directory. **REQUIRED**
        destination: The new path of the file or directory. **REQUIRED**
        overwrite: Set to True to allow overwriting an existing destination.
                   If False (default) and destination exists, the operation will fail.

    Examples:
        move_file(source="old_name.py", destination="new_name.py")
        move_file(source="file.txt", destination="folder/file.txt", overwrite=True)
    """
    if not source or not destination:
        return "Error: Missing arguments. Both 'source' and 'destination' are required."

    try:
        source_absolute = await resolve_and_validate_path(source, config)
        dest_absolute = await resolve_and_validate_path(destination, config)

        if not os.path.exists(source_absolute):
            return f"Error: Source path '{source}' does not exist."

        if os.path.exists(dest_absolute) and not overwrite:
            return (
                f"Error: Destination '{destination}' already exists. "
                "To overwrite it, you must pass overwrite=True."
            )

        # Perform the move via the File Center
        result = move_path(source_absolute, dest_absolute)
        if not result.success:
            return f"Error moving file: {result.message}"

        return f"Successfully moved '{source}' to '{destination}'."
    except Exception as e:
        return f"Error moving file: {e}"
