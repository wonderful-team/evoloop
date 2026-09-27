"""MCP config 模型单元测试。

覆盖：is_sse_url、McpServerConfig 构建/校验/DB 转换、AuthType 枚举、
ConnectionState / ConnectionResult / ServerCapabilities。
"""

from __future__ import annotations

import pytest

from app.core.mcp.config import (
    AuthType,
    ConnectionResult,
    ConnectionState,
    McpServerConfig,
    ServerCapabilities,
    TransportType,
    is_sse_url,
)


class TestIsSseUrl:
    def test_http_urls(self) -> None:
        assert is_sse_url("http://localhost:8080/mcp") is True
        assert is_sse_url("https://example.com/mcp") is True

    def test_non_http(self) -> None:
        assert is_sse_url("npx @modelcontextprotocol/server-filesystem") is False
        assert is_sse_url("node server.js") is False
        assert is_sse_url(None) is False
        assert is_sse_url("") is False


class TestMcpServerConfig:
    def test_stdio_defaults(self) -> None:
        cfg = McpServerConfig(name="srv", command="npx foo")
        assert cfg.transport == TransportType.STDIO
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.auth_type == AuthType.NONE
        assert cfg.enabled is True
        cfg.validate()  # 不应抛错

    def test_validate_stdio_requires_command(self) -> None:
        cfg = McpServerConfig(name="srv")
        with pytest.raises(ValueError, match="command is required"):
            cfg.validate()

    def test_validate_sse_requires_url(self) -> None:
        cfg = McpServerConfig(
            name="srv", transport=TransportType.SSE, url="http://x/mcp"
        )
        cfg.validate()  # ok

        bad = McpServerConfig(name="srv", transport=TransportType.SSE, url=None)
        with pytest.raises(ValueError, match="url is required"):
            bad.validate()

    def test_from_db_model_stdio(self) -> None:
        server = _DbServer(
            name="github",
            command="npx @github/mcp",
            args='["--token", "x"]',
            env='{"K": "V"}',
            enabled=True,
        )
        cfg = McpServerConfig.from_db_model(server)
        assert cfg.transport == TransportType.STDIO
        assert cfg.command == "npx @github/mcp"
        assert cfg.args == ["--token", "x"]
        assert cfg.env == {"K": "V"}
        assert cfg.url is None

    def test_from_db_model_sse(self) -> None:
        """/sse 结尾 = SSE 约定；/mcp 结尾 = Streamable HTTP（见 is_streamable_http_url）。"""
        server = _DbServer(
            name="mall",
            command="https://example.com/sse",
            args=None,
            env=None,
            enabled=True,
        )
        cfg = McpServerConfig.from_db_model(server)
        assert cfg.transport == TransportType.SSE
        assert cfg.url == "https://example.com/sse"

    def test_from_db_model_streamable_http(self) -> None:
        """/mcp 结尾的 URL 按约定识别为 Streamable HTTP。"""
        server = _DbServer(
            name="mall",
            command="https://example.com/mcp",
            args=None,
            env=None,
            enabled=True,
        )
        cfg = McpServerConfig.from_db_model(server)
        assert cfg.transport == TransportType.STREAMABLE_HTTP
        assert cfg.url == "https://example.com/mcp"

    def test_from_db_model_invalid_json_parses_to_defaults(self) -> None:
        server = _DbServer(
            name="srv",
            command="npx foo",
            args="{not valid json",
            env="not json either",
            enabled=True,
        )
        cfg = McpServerConfig.from_db_model(server)
        assert cfg.args == []
        assert cfg.env == {}


class _DbServer:
    """最小 McpServer ORM 替身（仅含 from_db_model 用到的字段）。"""

    def __init__(self, name, command, args, env, enabled):
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.enabled = enabled


class TestValueModels:
    def test_connection_state(self) -> None:
        st = ConnectionState(
            server_name="srv", is_connected=True, tools_count=3, error_message=None
        )
        assert st.server_name == "srv"
        assert st.last_health_check is None

    def test_connection_result(self) -> None:
        r = ConnectionResult(success=True, server_name="srv", tools_count=5)
        assert r.success is True
        assert r.error is None
        assert r.capabilities is None
        r2 = ConnectionResult(success=False, server_name="srv", error="boom")
        assert r2.error == "boom"

    def test_server_capabilities_dynamic(self) -> None:
        c = ServerCapabilities(tools=True, resources=False)
        assert c.tools is True
        assert c.resources is False


class TestAuthType:
    def test_values(self) -> None:
        assert AuthType.NONE == "none"
        assert AuthType.API_KEY == "api_key"
        assert AuthType.OAUTH_AUTHORIZATION_CODE == "oauth_auth_code"
        assert AuthType.OAUTH_DEVICE_CODE == "oauth_device_code"
