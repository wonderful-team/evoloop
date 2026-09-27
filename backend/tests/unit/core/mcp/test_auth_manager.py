"""MCP 认证（auth/manager.py / auth/elicitation.py）单元测试。

覆盖：McpAuthManager 处理器创建/认证/令牌/headers/回调、McpElicitationHandler
的解析/等待/提供/取消/超时。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.mcp.auth.base import AuthToken
from app.core.mcp.auth.elicitation import McpElicitationHandler
from app.core.mcp.auth.manager import McpAuthManager

_FUTURE = 4102444800  # 2100 年，远超当前时间戳


class TestMcpAuthManager:
    def test_create_handler_api_key_returns_none(self):
        mgr = McpAuthManager()
        h = mgr.create_handler("srv", {"method": "api_key"})
        assert h is None

    def test_create_handler_auth_code(self):
        mgr = McpAuthManager()
        h = mgr.create_handler(
            "srv",
            {
                "method": "oauth_authorization_code",
                "client_id": "cid",
                "authorization_endpoint": "https://auth/authorize",
                "token_endpoint": "https://auth/token",
            },
        )
        assert h is not None
        assert mgr._handlers["srv"] is h

    def test_create_handler_device_code(self):
        mgr = McpAuthManager()
        h = mgr.create_handler(
            "srv",
            {
                "method": "oauth_device_code",
                "client_id": "cid",
                "device_authorization_endpoint": "https://auth/device",
                "token_endpoint": "https://auth/token",
            },
        )
        assert h is not None

    def test_create_handler_unknown_returns_none(self):
        mgr = McpAuthManager()
        assert mgr.create_handler("srv", {"method": "bogus"}) is None

    async def test_authenticate_stores_token(self):
        mgr = McpAuthManager()
        handler = MagicMock()
        handler.authenticate = AsyncMock(return_value=AuthToken(access_token="tok"))
        mgr._handlers["srv"] = handler
        token = await mgr.authenticate("srv")
        assert token.access_token == "tok"
        assert mgr._tokens["srv"] is token

    async def test_authenticate_no_handler(self):
        mgr = McpAuthManager()
        assert await mgr.authenticate("srv") is None

    async def test_get_token_refreshes_when_expired(self):
        mgr = McpAuthManager()
        old = AuthToken(access_token="old", refresh_token="rt", expires_in=0)
        new = AuthToken(access_token="new", refresh_token="rt2", expires_in=_FUTURE)
        handler = MagicMock()
        handler.refresh = AsyncMock(return_value=new)
        mgr._handlers["srv"] = handler
        mgr._tokens["srv"] = old
        token = await mgr.get_token("srv")
        assert token.access_token == "new"
        handler.refresh.assert_awaited_once()

    async def test_get_token_missing(self):
        mgr = McpAuthManager()
        assert await mgr.get_token("srv") is None

    async def test_get_headers(self):
        mgr = McpAuthManager()
        token = AuthToken(access_token="abc", token_type="Bearer")
        handler = MagicMock()
        handler.get_headers.return_value = {"Authorization": "Bearer abc"}
        mgr._handlers["srv"] = handler
        mgr._tokens["srv"] = token
        assert mgr.get_headers("srv") == {"Authorization": "Bearer abc"}

    async def test_handle_oauth_callback(self):
        mgr = McpAuthManager()
        from app.core.mcp.auth.oauth_flows import OAuthAuthorizationCodeHandler

        handler = MagicMock(spec=OAuthAuthorizationCodeHandler)
        handler.handle_callback = AsyncMock()
        mgr._handlers["srv"] = handler
        await mgr.handle_oauth_callback("srv", "http://callback?code=x")
        handler.handle_callback.assert_awaited_once_with("http://callback?code=x")

    async def test_handle_oauth_callback_no_handler(self):
        mgr = McpAuthManager()
        with pytest.raises(ValueError, match="No OAuth handler"):
            await mgr.handle_oauth_callback("srv", "url")

    def test_remove_handler(self):
        mgr = McpAuthManager()
        mgr._handlers["srv"] = MagicMock()
        mgr._tokens["srv"] = MagicMock()
        mgr.remove_handler("srv")
        assert "srv" not in mgr._handlers
        assert "srv" not in mgr._tokens


class TestMcpElicitationHandler:
    def test_parse_elicitation_error(self):
        h = McpElicitationHandler()
        req = h.parse_elicitation_error(
            "srv",
            {
                "elicitation": {
                    "message": "Need config",
                    "required": ["token"],
                    "fields": {"token": {"description": "API token", "sensitive": True}},
                }
            },
        )
        assert req.server_name == "srv"
        assert req.message == "Need config"
        assert req.fields[0].name == "token"
        assert req.fields[0].sensitive is True
        assert h.has_pending("srv")

    def test_parse_elicitation_defaults(self):
        h = McpElicitationHandler()
        req = h.parse_elicitation_error("srv", {})
        assert req.message == "Additional configuration required"
        assert req.fields == []

    def test_get_pending(self):
        h = McpElicitationHandler()
        h.parse_elicitation_error("srv", {"elicitation": {"required": ["a"]}})
        assert h.get_pending("srv") is not None
        assert h.get_pending("missing") is None

    async def test_wait_and_provide(self):
        h = McpElicitationHandler()
        h.parse_elicitation_error("srv", {"elicitation": {}})

        async def waiter():
            return await h.wait_for_input("srv", timeout=5)

        task = asyncio.ensure_future(waiter())
        await asyncio.sleep(0.01)
        h.provide_input("srv", SimpleNamespace(data={"token": "abc"}))
        result = await task
        assert result.data == {"token": "abc"}
        assert not h.has_pending("srv")

    async def test_wait_no_pending_raises(self):
        h = McpElicitationHandler()
        with pytest.raises(ValueError, match="No pending elicitation"):
            await h.wait_for_input("srv")

    async def test_wait_timeout(self):
        h = McpElicitationHandler()
        h.parse_elicitation_error("srv", {"elicitation": {}})
        with pytest.raises(RuntimeError, match="Elicitation timeout"):
            await h.wait_for_input("srv", timeout=0.01)

    def test_provide_no_future_raises(self):
        h = McpElicitationHandler()
        with pytest.raises(ValueError, match="No pending elicitation"):
            h.provide_input("srv", SimpleNamespace(data={}))

    async def test_cancel(self):
        h = McpElicitationHandler()
        h.parse_elicitation_error("srv", {"elicitation": {}})
        future = h._futures["srv"] = asyncio.get_running_loop().create_future()
        h.cancel("srv")
        assert future.cancelled() is True
        assert not h.has_pending("srv")
