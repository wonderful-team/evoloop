"""极简自包含 MCP stdio 服务器，供 MCP 链路 e2e 测试使用。

只依赖 `mcp` 包（fastmcp），不 import 应用代码，保证测试进程可独立拉起。
提供工具/资源/提示三类能力，覆盖客户端 features 初始化链路。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Mini E2E MCP Server")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input text back with a prefix."""
    return f"echo:{text}"


@mcp.resource("greeting://default")
def greeting_resource() -> str:
    """Default greeting resource."""
    return "Hello from Mini E2E MCP Server"


@mcp.prompt()
def summarize(text: str) -> str:
    """Build a summarization prompt for the given text."""
    return f"Please summarize the following text:\n\n{text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
