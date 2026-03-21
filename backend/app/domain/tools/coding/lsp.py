import asyncio
import logging
import os
from pathlib import Path
from typing import Literal, Optional

from langchain_core.runnables import RunnableConfig

from app.core.tools import evoloop_tool, get_working_directory
from app.infrastructure.solidlsp.language_servers.clangd_language_server import (
    ClangdLanguageServer,
)
from app.infrastructure.solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS
from app.infrastructure.solidlsp.language_servers.gopls import Gopls
from app.infrastructure.solidlsp.language_servers.intelephense import Intelephense
from app.infrastructure.solidlsp.language_servers.pyright_server import PyrightServer
from app.infrastructure.solidlsp.language_servers.rust_analyzer import RustAnalyzer
from app.infrastructure.solidlsp.language_servers.typescript_language_server import (
    TypeScriptLanguageServer,
)
from app.infrastructure.solidlsp.language_servers.vue_language_server import (
    VueLanguageServer,
)
from app.infrastructure.solidlsp.ls import SolidLanguageServer
from app.infrastructure.solidlsp.ls_config import Language, LanguageServerConfig
from app.infrastructure.solidlsp.settings import SolidLSPSettings

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
        elif language_str.lower() == "go":
            language = Language.GO
            server_class = Gopls
        elif language_str.lower() == "rust":
            language = Language.RUST
            server_class = RustAnalyzer
        elif language_str.lower() == "java":
            language = Language.JAVA
            server_class = EclipseJDTLS
        elif language_str.lower() in ["c", "cpp", "c++"]:
            language = Language.CPP
            server_class = ClangdLanguageServer
        elif language_str.lower() == "php":
            language = Language.PHP
            server_class = Intelephense
        elif language_str.lower() == "vue":
            language = Language.VUE
            server_class = VueLanguageServer
        else:
            raise ValueError(f"Unsupported language for LSP: {language_str}")

        config = LanguageServerConfig(code_language=language)

        # Instantiate server
        server = server_class(
            config=config,
            repository_root_path=repo_path,
            solidlsp_settings=self.solidlsp_settings,
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
                server.shutdown()  # Sends exit notification
                server.stop()  # Kills process
            except Exception as e:
                log.error(f"Error shutting down LSP server {key}: {e}")
        self.servers.clear()


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.search_code",
    name_map={"zh": "咨询LSP", "en": "Consult LSP"}
)
async def consult_lsp(
    action: Literal["check_errors", "find_definition", "hover"],
    file_path: str,
    line: int | None = None,  # 1-indexed
    character: int | None = None,  # 1-indexed
    config: RunnableConfig | None = None,
) -> str:
    """
    Consult the Language Server Protocol (LSP) for code intelligence.
    Use this to check for errors, find definitions, or get hover information.

    Args:
        action: The action to perform.
        file_path: Path to the file (Relative to project root or Absolute).
        line: 1-indexed line number.
        character: 1-indexed character/column number.
    """

    # Path Resolution Logic with Context Awareness
    project_root = Path(get_working_directory(config)).resolve()

    candidates = []
    # 1. Try resolving relative to Project Root (Most likely for Agent)
    candidates.append((project_root / file_path).resolve())

    # 2. Try as provided (Absolute or relative to CWD)
    candidates.append(Path(file_path).resolve())

    file_path_obj = None
    for cand in candidates:
        if cand.exists():
            file_path_obj = cand
            break

    if not file_path_obj:
        return f"Error: File {file_path} does not exist. Searched in: {[str(c) for c in candidates]}. Project Root: {project_root}"

    repo_root = _find_repo_root(file_path_obj)
    if not repo_root:
        # Fallback using project_root from context if it looks like a repo
        if (project_root / ".git").exists():
            repo_root = project_root
        else:
            repo_root = file_path_obj.parent

    # Determine language
    suffix = file_path_obj.suffix.lower()
    if suffix in [".py"]:
        language = "python"
    elif suffix in [".ts", ".tsx", ".js", ".jsx"]:
        language = "typescript"
    elif suffix in [".go"]:
        language = "go"
    elif suffix in [".rs"]:
        language = "rust"
    elif suffix in [".java"]:
        language = "java"
    elif suffix in [".c", ".cpp", ".h", ".hpp", ".cc"]:
        language = "c++"
    elif suffix in [".php"]:
        language = "php"
    elif suffix in [".vue"]:
        language = "vue"
    else:
        return f"Error: Unsupported language for file extension {suffix}"

    manager = LSPManager.get_instance()
    try:
        server = manager.get_server(language, str(repo_root))
    except Exception as e:
        log.error(f"Failed to start LSP server: {e}")
        return f"Error: Failed to start LSP server: {e}"

    relative_path = os.path.relpath(str(file_path_obj), repo_root)

    # Ensure file is open in LSP
    # SolidLSP manages ref counts via `open_file` context manager usually.
    # But for persistent server, we might want to just open it if not open.
    # Let's use `open_file` context manager to ensure it's "open" during the operation.

    try:
        # LSP uses 0-indexed line/col
        idx_line = (line - 1) if line else 0
        idx_char = (character - 1) if character else 0

        if action == "check_errors":
            # We must open the file to ensure LSP analyzes it (especially for single file analysis or new files)
            # The 'with' block sends didOpen and didClose.
            with server.open_file(relative_path):
                # Wait for diagnostics to populate?
                # Diagnostics are asynchronous. We can poll briefly.
                diagnostics = []
                for _ in range(20):  # Wait up to 2 seconds
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
                rng = d.get("range", {})
                start = rng.get("start", {})
                start_line = start.get("line", -1) + 1

                severity = d.get("severity", 1)  # Default to Error
                severity_map = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
                severity_str = severity_map.get(severity, "Error")

                message = d.get("message", "No message")
                # Filter out "Analysis complete" style messages if any? No, diagnostics are errors.

                source = d.get("source", "LSP")

                result.append(f"Line {start_line}: [{severity_str}] {message} (Source: {source})")

            return "\n".join(result)

        elif action == "find_definition":
            if line is None or character is None:
                return "Error: line and character arguments are required for find_definition."

            locations = server.request_definition(relative_path, idx_line, idx_char)
            if not locations:
                return "No definitions found."

            result = []
            for loc in locations:
                path = loc.get("absolutePath")
                if not path and "uri" in loc:
                    # simplistic uri to path
                    path = loc["uri"].replace("file://", "")

                rng = loc.get("range", {})
                start_val = rng.get("start", {}).get("line", 0) + 1

                result.append(f"{path}:{start_val}")

            return "\n".join(result)

        elif action == "hover":
            if line is None or character is None:
                return "Error: line and character arguments are required for hover."

            hover_data = server.request_hover(relative_path, idx_line, idx_char)
            if not hover_data:
                return "No hover information found."

            # Hover contents can be MarkedString, MarkedString[], or MarkupContent
            contents = hover_data.get("contents")
            if not contents:
                return "Empty hover content."

            hover_text = ""
            if isinstance(contents, dict):  # MarkupContent
                hover_text = contents.get("value", "")
            elif isinstance(contents, list):  # Array<MarkedString>
                parts = []
                for item in contents:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.append(item.get("value", ""))
                hover_text = "\n\n".join(parts)
            elif isinstance(contents, str):
                hover_text = contents

            return hover_text

        else:
            return f"Error: Unknown action '{action}'"

    except Exception as e:
        log.error(f"LSP action failed: {e}", exc_info=True)
        return f"Error during LSP action: {e}"


def _find_repo_root(path: Path) -> Path | None:
    current = path
    if current.is_file():
        current = current.parent
    for _ in range(10):  # Depth limit
        if (current / ".git").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None
