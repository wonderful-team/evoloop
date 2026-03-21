import ast
import importlib.util
import logging
import os

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.tools import evoloop_tool
from app.core.tools.runtime_registry import register_runtime_tool

logger = logging.getLogger(__name__)

DYNAMIC_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "../../../tools/dynamic")

# Ensure directory exists
os.makedirs(DYNAMIC_TOOLS_DIR, exist_ok=True)
init_file = os.path.join(DYNAMIC_TOOLS_DIR, "__init__.py")
if not os.path.exists(init_file):
    with open(init_file, "w") as f:
        f.write("")


class SafeASTVisitor(ast.NodeVisitor):
    """
    AST Visitor to enforce strict security policies on dynamic tools.
    Forbids dangerous imports and function calls.
    """

    def __init__(self):
        self.errors = []
        self.allowed_imports = {
            "json",
            "math",
            "datetime",
            "re",
            "random",
            "typing",
            "collections",
            "itertools",
            "functools",
        }
        # Whitelist safe builtins if needed, but for now we blacklist dangerous ones.
        self.unsafe_functions = {"eval", "exec", "compile", "open", "input"}

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split(".")[0] not in self.allowed_imports:
                self.errors.append(f"Import forbidden: '{alias.name}'. Allowed: {self.allowed_imports}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.split(".")[0] not in self.allowed_imports:
            self.errors.append(f"Import forbidden: '{node.module}'. Allowed: {self.allowed_imports}")
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for banned functions like eval(), exec(), open()
        if isinstance(node.func, ast.Name):
            if node.func.id in self.unsafe_functions:
                self.errors.append(f"Function call forbidden: '{node.func.id}()'")

        # Check for os.system, subprocess.run etc.
        elif isinstance(node.func, ast.Attribute):
            # Hard to catch everything, but we block imports so 'os.system' fails at import level.
            # Double check for attributes if someone passes module as arg?
            pass

        self.generic_visit(node)


class CreatePythonToolInput(BaseModel):
    name: str = Field(..., description="The name of the tool (snake_case), e.g., 'calculate_hash'.")
    description: str = Field(..., description="A clear description of what the tool does and its arguments.")
    code: str = Field(..., description="The Python code defining the function. MUST include type hints and a docstring.")
    version: str | None = Field("1.0.0", description="Version string.")


@evoloop_tool(
    "create_python_tool",
    args_schema=CreatePythonToolInput,
    is_state_mutating=True,
    name_map={"zh": "创建Python工具", "en": "Create Python Tool"}
)
def create_python_tool(name: str, description: str, code: str, version: str = "1.0.0") -> str:
    """
    Creates a new Python tool at runtime.
    The tool will be saved to disk, loaded, and made available for immediate use.

    WARNING: The code runs in the host environment. Do not use for untrusted code if not sandboxed.
    """
    if not name.isidentifier():
        return f"Error: Tool name '{name}' is not a valid Python identifier."

    # 1. Safety Check (AST Visitor)
    try:
        tree = ast.parse(code)
        validator = SafeASTVisitor()
        validator.visit(tree)
        if validator.errors:
            return "Security Error: Unsafe code detected.\n" + "\n".join(validator.errors)
    except SyntaxError as e:
        return f"Error: Code has syntax errors: {e}"

    # 2. Save Code
    filename = f"{name}.py"
    filepath = os.path.join(DYNAMIC_TOOLS_DIR, filename)

    try:
        with open(filepath, "w") as f:
            f.write(code)
    except Exception as e:
        return f"Error writing tool file: {e}"

    # 3. Dynamic Import
    try:
        spec = importlib.util.spec_from_file_location(name, filepath)
        if spec is None or spec.loader is None:
            return f"Error: Could not create import spec for {filepath}"

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 4. Find the function
        # We assume the function name matches the tool name OR there is only one function.
        target_func = getattr(module, name, None)

        if not target_func:
            # Fallback: Find the first function in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and not attr_name.startswith("_") and attr_name != "tool":
                    target_func = attr
                    break

        if not target_func:
            return f"Error: Could not find a callable function in the provided code. Ensure function name matches '{name}'."

        # 5. Wrap as LangChain Tool
        # Use StructuredTool.from_function to inspect type hints automatically
        new_tool = StructuredTool.from_function(
            func=target_func,
            name=name,
            description=description
        )

        # 6. Register
        register_runtime_tool(new_tool)

        return f"Success: Tool '{name}' created and registered. You can now use it."

    except Exception as e:
        logger.error(f"Failed to load dynamic tool {name}: {e}")
        return f"Error loading tool: {e}"
