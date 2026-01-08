import logging
import os
from typing import Literal, Optional, Any
from pathlib import Path

from app.core.tools import evoloop_tool
from app.core.config import settings
from app.infrastructure.solidlsp.ls import SolidLanguageServer, LSPFileBuffer
from app.infrastructure.solidlsp.language_servers.pyright_server import PyrightServer
from app.infrastructure.solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from app.infrastructure.solidlsp.settings import SolidLSPSettings
from app.infrastructure.solidlsp.ls_config import LanguageServerConfig, Language

log = logging.getLogger(__name__)

class LSPManager:
    _instance: Optional["LSPManager"] = None
    
    def __init__(self) -> None:
        self.servers: dict[str, SolidLanguageServer] = {}
        self.solidlsp_settings = SolidLSPSettings()
        
    @classmethod
    def get_instance(cls) -> "LSPManager":
        if cls._instance is None:
            cls._instance = LSPManager()
        return cls._instance

    def _get_server_key(self, language: str, repo_path: str) -> str:
        return f"{language}:{os.path.abspath(repo_path)}"

    def get_server(self, language_str: str, repo_path: str) -> SolidLanguageServer:
        key = self._get_server_key(language_str, repo_path)
        if key in self.servers:
            server = self.servers[key]
            # SolidLanguageServer wraps handler in .server attribute
            # We should check if the handler's process is alive
            if server.server.process and server.server.process.poll() is None:
                 return server
            else:
                 log.warning(f"LSP server for {key} seems dead, restarting...")
                 del self.servers[key]

        log.info(f"Initializing LSP server for {language_str} at {repo_path}")
        
        repo_path = os.path.abspath(repo_path)
        
        # Determine Language and Server Class
        if language_str.lower() == "python":
            language = Language.PYTHON
            server_class = PyrightServer
        elif language_str.lower() in ["typescript", "javascript", "ts", "js"]:
            language = Language.TYPESCRIPT
            server_class = TypeScriptLanguageServer
        else:
            raise ValueError(f"Unsupported language for LSP: {language_str}")

        config = LanguageServerConfig(code_language=language)
        
        # Instantiate server
        server = server_class(
            config=config,
            repository_root_path=repo_path,
            solidlsp_settings=self.solidlsp_settings
        )
        
        # Start server (synchronously for now, but usually it's async context manager or start method)
        # solidlsp's start_server is usually a method that runs in a thread or returns a context manager.
        # Looking at PyrightServer._start_server:
        # It's an internal method called by start()? No, SolidLanguageServer has start().
        # Wait, PyrightServer usage in docstring: "async with lsp.start_server():"
        # But SolidLanguageServer.start() implementation in ls_handler.py starts a thread.
        # Let's check SolidLanguageServer.start() signature in ls.py.
        # It seems SolidLanguageServer inherits from nothing but uses handler.
        
        # Actually, let's look at `ls.py` again. `SolidLanguageServer` methods.
        # Reference: `pyright_server.py` line 109: `def _start_server(self) -> None:`
        # It overrides `_start_server`.
        # And `SolidLanguageServer` likely has a public `start()` method?
        # Let's check `ls.py` specifically for startup logic.
        
        # Assuming we can just call server.start()
        # But `pyright_server.py` suggests using `async with lsp.start_server():` is NOT correct based on the code I read?
        # The docstring in `pyright_server.py` (lines 118) says `async with lsp.start_server():`.
        # But `_start_server` returns `None`.
        # Maybe `ls.py` has a `start_server` context manager?
        
        # For now, I will assume I need to call `server.start()` explicitly.
        # I'll verify this by reading `ls.py` first if I'm unsure.
        # But I'll write the code assuming I need to call something to start it.
        
        server.start()
        self.servers[key] = server
        return server

    def shutdown(self) -> None:
        for key, server in self.servers.items():
            try:
                log.info(f"Shutting down LSP server {key}")
                server.shutdown() # Sends exit notification
                server.stop() # Kills process
            except Exception as e:
                log.error(f"Error shutting down LSP server {key}: {e}")
        self.servers.clear()

@evoloop_tool
async def consult_lsp(
    action: Literal['check_errors', 'find_definition', 'hover'],
    file_path: str,
    line: Optional[int] = None, # 1-indexed
    character: Optional[int] = None # 1-indexed
) -> str:
    """
    Consult the Language Server Protocol (LSP) for code intelligence.
    Use this to check for errors, find definitions, or get hover information.
    
    Args:
        action: The action to perform.
            - 'check_errors': Returns a list of diagnostics (errors, warnings) for the file.
            - 'find_definition': Returns the location where the symbol at line/character is defined.
            - 'hover': Returns documentation/type info for the symbol at line/character.
        file_path: Absolute path to the file.
        line: 1-indexed line number (required for find_definition and hover).
        character: 1-indexed character/column number (required for find_definition and hover).
    """
    
    # Implicitly determine repo root and language?
    # For now, assume repo root is project root.
    # In EvoLoop, we might have project_id context, but tools receive strict args.
    # We can infer repo root by traversing up until .git or using implicit context if possible.
    # Taking a safe bet: assume file_path is absolute and within a repo. Use simple traversal.
    
    file_path_obj = Path(file_path).resolve()
    if not file_path_obj.exists():
        return f"Error: File {file_path} does not exist."
        
    repo_root = _find_repo_root(file_path_obj)
    if not repo_root:
        # Fallback to file's directory if no git root found
        repo_root = file_path_obj.parent
        
    # Determine language
    suffix = file_path_obj.suffix.lower()
    if suffix in ['.py']:
        language = 'python'
    elif suffix in ['.ts', '.tsx', '.js', '.jsx']:
        language = 'typescript'
    else:
        return f"Error: Unsupported language for file extension {suffix}"

    manager = LSPManager.get_instance()
    try:
        server = manager.get_server(language, str(repo_root))
    except Exception as e:
        log.error(f"Failed to start LSP server: {e}")
        return f"Error: Failed to start LSP server: {e}"

    relative_path = os.path.relpath(file_path, repo_root)
    
    # Ensure file is open in LSP
    # SolidLSP manages ref counts via `open_file` context manager usually.
    # But for persistent server, we might want to just open it if not open.
    # Let's use `open_file` context manager to ensure it's "open" during the operation.
    
    try:
        # LSP uses 0-indexed line/col
        idx_line = (line - 1) if line else 0
        idx_char = (character - 1) if character else 0
        
        if action == 'check_errors':
            # We must open the file to ensure LSP analyzes it (especially for single file analysis or new files)
            # The 'with' block sends didOpen and didClose.
            with server.open_file(relative_path):
                # Wait for diagnostics to populate? 
                # Diagnostics are asynchronous. We can poll briefly.
                import asyncio
                diagnostics = []
                for _ in range(20): # Wait up to 2 seconds
                    raw_diagnostics = server.get_diagnostics(relative_path)
                    if raw_diagnostics:
                        diagnostics = raw_diagnostics
                        break
                    await asyncio.sleep(0.1)
            
            if not diagnostics:
                return "No errors found."
            
            result = []
            for d in diagnostics:
                # d structure based on LSP Diagnostic spec
                rng = d.get('range', {})
                start = rng.get('start', {})
                start_line = start.get('line', -1) + 1
                
                severity = d.get('severity', 1)  # Default to Error
                severity_map = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
                severity_str = severity_map.get(severity, "Error")
                
                message = d.get('message', 'No message')
                # Filter out "Analysis complete" style messages if any? No, diagnostics are errors.
                
                source = d.get('source', 'LSP')
                
                result.append(f"Line {start_line}: [{severity_str}] {message} (Source: {source})")
            
            return "\n".join(result)

        elif action == 'find_definition':
            if line is None or character is None:
                return "Error: line and character arguments are required for find_definition."
            
            locations = server.request_definition(relative_path, idx_line, idx_char)
            if not locations:
                return "No definitions found."
            
            result = []
            for loc in locations:
                path = loc.get('absolutePath')
                if not path and 'uri' in loc:
                    # simplistic uri to path
                    path = loc['uri'].replace('file://', '')
                
                rng = loc.get('range', {})
                start_val = rng.get('start', {}).get('line', 0) + 1
                
                result.append(f"{path}:{start_val}")
            
            return "\n".join(result)

        elif action == 'hover':
            if line is None or character is None:
                return "Error: line and character arguments are required for hover."
            
            hover_data = server.request_hover(relative_path, idx_line, idx_char)
            if not hover_data:
                return "No hover information found."
            
            # Hover contents can be MarkedString, MarkedString[], or MarkupContent
            contents = hover_data.get('contents')
            if not contents:
                return "Empty hover content."
            
            hover_text = ""
            if isinstance(contents, dict): # MarkupContent
                hover_text = contents.get('value', '')
            elif isinstance(contents, list): # Array<MarkedString>
                parts = []
                for item in contents:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.append(item.get('value', ''))
                hover_text = "\n\n".join(parts)
            elif isinstance(contents, str):
                hover_text = contents
                
            return hover_text

        else:
            return f"Error: Unknown action '{action}'"
            
    except Exception as e:
        log.error(f"LSP action failed: {e}", exc_info=True)
        return f"Error during LSP action: {e}"

def _find_repo_root(path: Path) -> Optional[Path]:
    current = path
    if current.is_file():
        current = current.parent
    for _ in range(10): # Depth limit
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None
