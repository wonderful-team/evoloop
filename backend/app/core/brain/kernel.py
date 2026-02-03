"""
The Cognitive Kernel (Context OS).
Manages the interaction between the File System (Memory) and the Drivers (Compute).
"""
import logging
import re
from typing import Optional

from app.core.config import settings
from app.core.brain.drivers.abstract import BaseBrainDriver
from app.core.brain.filesystem.manager import BrainFileSystem
from app.core.brain.filesystem.protocol import MemoryFile, MemoryZone

logger = logging.getLogger(__name__)

class LightningKernel:
    """
    The 'Operating System' that runs the agent loop.
    """
    
    def __init__(self, 
                 ssm_driver: BaseBrainDriver, 
                 fs_manager: BrainFileSystem, 
                 reflective_driver: Optional[BaseBrainDriver] = None):
        self.fast = ssm_driver
        self.slow = reflective_driver
        self.fs = fs_manager
        
    async def initialize(self):
        """Boot sequence."""
        self.fs.initialize()
        # Initialize Fast System (SSM)
        await self.fast.initialize()
        
        # Ensure Identity exists
        identity_path = f"{MemoryZone.SYS.value}/{MemoryFile.IDENTITY.value}"
        if not self.fs._validate_path(identity_path).exists():
            self.fs.write_file(identity_path, "You are evolooop, an intelligent coding assistant.")
            
    def _load_context(self) -> str:
        """
        Paging mechanism: Decides what files to load into RAM (Context Window).
        For v1, we load Identity and Current Task.
        """
        context = []
        
        # 1. System Identity
        identity = self.fs.read_file(f"{MemoryZone.SYS.value}/{MemoryFile.IDENTITY.value}")
        context.append(f"<SYSTEM_IDENTITY>\n{identity}\n</SYSTEM_IDENTITY>")
        
        # 2. Working Memory
        task = self.fs.read_file(f"{MemoryZone.WORKING.value}/{MemoryFile.TASK.value}")
        if not task.startswith("[Error"):
             context.append(f"<CURRENT_TASK>\n{task}\n</CURRENT_TASK>")
             
        return "\n".join(context)

    def _parse_tool_call(self, output: str):
        """
        Naive regex parser for XML-style tool calls.
        Format: <cmd>func_name arg1="val1"</cmd>
        This is a simplified parser for the prototype.
        """
        # Example: <cmd>write_file path="foo.md" content="bar"</cmd>
        # Just detecting if there is a tag for now
        if "<cmd>" in output and "</cmd>" in output:
            start = output.find("<cmd>") + 5
            end = output.find("</cmd>")
            content = output[start:end].strip()
            
            # Very basic string split parsing (Robust parsing would use regex or grammar)
            # Assuming format: command path="Helper"
            parts = content.split(" ", 1)
            cmd_name = parts[0]
            args_str = parts[1] if len(parts) > 1 else ""
            
            return cmd_name, args_str
            
        return None, None

    async def _execute_tool(self, cmd_name: str, args_str: str) -> str:
        """Executes internal file system tools."""
        logger.info(f"Kernel executing tool: {cmd_name} args={args_str}")
        
        # Simple parser for args: path="val" content="val"
        # This is fragile, for prototype only
        import shlex
        try:
            # Hacky way to parse key="value" strings into dict
            # user shlex to handle quotes
            tokens = shlex.split(args_str)
            kwargs = {}
            for token in tokens:
                if "=" in token:
                    k, v = token.split("=", 1)
                    kwargs[k] = v
        except Exception as e:
            return f"Error parsing arguments: {e}"

        if cmd_name == "read_file":
            return self.fs.read_file(kwargs.get("path", ""))
        elif cmd_name == "write_file":
            return self.fs.write_file(kwargs.get("path", ""), kwargs.get("content", ""))
        elif cmd_name == "list_files":
            files = self.fs.list_files(kwargs.get("path", "."))
            return "\n".join(files)
        elif cmd_name == "search_files":
            results = self.fs.search_files(kwargs.get("query", ""))
            return "\n".join(results)
            
        return f"Unknown tool: {cmd_name}"

    async def step(self, user_input: str, max_depth: int = 3, system_prompt: Optional[str] = None) -> str:
        """
        The ReAct Loop.
        """
        if max_depth <= 0:
            return "Error: Max recursion depth reached."
            
        # 1. Paging
        context = self._load_context()
        
        # 2. Compute (SSM)
        response = await self.fast.generate(context, user_input, system_prompt=system_prompt)
        
        # 3. Tool Dispatch
        cmd, args = self._parse_tool_call(response)
        if cmd:
            observation = await self._execute_tool(cmd, args)
            
            # Recursion: Feed observation back to brain
            next_input = f"System Observation: {observation}\n(Continue previous thought)"
            # Note: In a real system we append to message history, here we just recurse
            return await self.step(next_input, max_depth=max_depth-1)
            
        return response
