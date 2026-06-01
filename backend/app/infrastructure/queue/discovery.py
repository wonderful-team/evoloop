"""Auto-discover task modules by scanning for @shared_task decorators."""
import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_task_modules: list[str] | None = None


def discover_task_modules() -> list[str]:
    """Walk app/ source tree, AST-parse every .py, return module paths
    that contain at least one ``@shared_task``-decorated function."""
    global _task_modules
    if _task_modules is not None:
        return _task_modules

    app_dir = Path(__file__).resolve().parent.parent.parent  # …/backend/app/
    modules: set[str] = set()

    for pyfile in sorted(app_dir.rglob("*.py")):
        if pyfile.name == "__init__.py":
            continue

        try:
            tree = ast.parse(pyfile.read_text("utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                # @shared_task or @shared_task(...)
                # @periodic_task or @periodic_task(...)
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name):
                    deco_name = deco.func.id
                elif isinstance(deco, ast.Name):
                    deco_name = deco.id
                else:
                    continue
                if deco_name not in ("shared_task", "periodic_task"):
                    continue

                rel = pyfile.relative_to(app_dir)
                mod = "app." + str(rel.with_suffix("")).replace("/", ".")
                modules.add(mod)
                break  # one match per file is enough

    result = sorted(modules)
    logger.info("[Discovery] Found %d task modules: %s", len(result), result)
    _task_modules = result
    return result
