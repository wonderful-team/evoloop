import os
from typing import Literal

from langchain_core.runnables import RunnableConfig

from app.utils.process import run_command as utils_run_cmd

from .utils import resolve_and_validate_path


async def handle_list(
    action: Literal["list", "list_tree"],
    path: str,
    max_depth: int = 3,
    with_symbols: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return f"Error: Path does not exist: {path}"

    if action == "list":
        # ls logic
        cmd = ["ls", target_path]
        res = utils_run_cmd(cmd)
        if not res.success:
            return f"Error: {res.stderr}"
        return res.stdout[:2000]

    elif action == "list_tree":
        # Delegate to AnnotatedTreeGenerator
        from app.core.context import AnnotatedTreeGenerator

        try:
            # Use provided max_depth and with_symbols
            generator = AnnotatedTreeGenerator(
                target_path,
                max_depth=max_depth,
                with_symbols=with_symbols,
                file_limit=30,
            )
            tree_output = await generator.generate()
            return tree_output
        except Exception as e:
            return f"Error generating tree: {e}"

    return f"Error: Unknown list action {action}"
