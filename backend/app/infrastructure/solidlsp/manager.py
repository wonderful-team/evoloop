import logging
import os
from typing import Optional

from app.infrastructure.solidlsp.language_servers.clangd_language_server import ClangdLanguageServer
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
