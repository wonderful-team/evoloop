"""Transport layer for MCP connections (stdio and SSE)."""

import logging
import os
import sys
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

from app.core.mcp.config import McpServerConfig, TransportType

logger = logging.getLogger(__name__)


@contextmanager
def restore_std_streams():
    """
    Temporarily restore sys.stdout and sys.stderr to original streams.
    This fixes issues where libraries (like Celery) monkey-patch stdout/stderr with proxies
    that don't implement fileno(), causing subprocess creation to fail.
    """
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        if hasattr(sys, "__stdout__") and sys.__stdout__:
            sys.stdout = sys.__stdout__
        if hasattr(sys, "__stderr__") and sys.__stderr__:
            sys.stderr = sys.__stderr__
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


class McpTransport:
    """Transport layer for MCP connections."""

    @staticmethod
    @asynccontextmanager
    async def create_transport(
        config: McpServerConfig,
    ) -> AsyncGenerator[tuple[Any, Any], None]:
        """
        Create transport (read/write streams) based on config.
        
        Args:
            config: Server configuration
            
        Yields:
            Tuple of (read_stream, write_stream)
        """
        if config.transport == TransportType.SSE or (
            config.command and (
                config.command.startswith("http://") or 
                config.command.startswith("https://")
            )
        ):
            # SSE transport
            url = config.url or config.command
            logger.info(f"Connecting via SSE to {url}")
            async with sse_client(url, headers=config.headers) as (read, write):
                yield read, write
                
        else:
            # Stdio transport
            full_env = os.environ.copy()
            full_env.update(config.env)
            
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=full_env
            )
            
            logger.info(f"Connecting via stdio to {config.command}")
            with restore_std_streams():
                async with stdio_client(server_params) as (read, write):
                    yield read, write

    @staticmethod
    async def create_session(
        read_stream: Any, 
        write_stream: Any
    ) -> ClientSession:
        """
        Create and initialize a ClientSession.
        
        Args:
            read_stream: Read stream from transport
            write_stream: Write stream from transport
            
        Returns:
            Initialized ClientSession
        """
        session = ClientSession(read_stream, write_stream)
        await session.initialize()
        return session
