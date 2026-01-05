
import os
import ast
import logging
import importlib.util
from typing import Optional, Type
from langchain_core.tools import tool, BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from app.domain.tools.runtime_registry import register_runtime_tool

logger = logging.getLogger("evoloop.tools.dynamic")

DYNAMIC_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "../../../tools/dynamic")

# Ensure directory exists
os.makedirs(DYNAMIC_TOOLS_DIR, exist_ok=True)
init_file = os.path.join(DYNAMIC_TOOLS_DIR, "__init__.py")
if not os.path.exists(init_file):
    with open(init_file, "w") as f:
        f.write("")

class CreatePythonToolInput(BaseModel):
    name: str = Field(..., description="The name of the tool (snake_case), e.g., 'calculate_hash'.")
    description: str = Field(..., description="A clear description of what the tool does and its arguments.")
    code: str = Field(..., description="The Python code defining the function. MUST include type hints and a docstring.")
    version: Optional[str] = Field("1.0.0", description="Version string.")

@tool("create_python_tool", args_schema=CreatePythonToolInput)
def create_python_tool(name: str, description: str, code: str, version: str = "1.0.0") -> str:
    """
    Creates a new Python tool at runtime.
    The tool will be saved to disk, loaded, and made available for immediate use.
    
    WARNING: The code runs in the host environment. Do not use for untrusted code if not sandboxed.
    """
    if not name.isidentifier():
        return f"Error: Tool name '{name}' is not a valid Python identifier."

    # 1. Safety Check (Basic AST)
    try:
        tree = ast.parse(code)
        # TODO: Add more checks (e.g. forbid 'os.system', 'subprocess' if enforcing strict safety)
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
