"""MCP OAuth 流程（auth/oauth_flows.py）单元测试。

覆盖：PKCE 生成、授权 URL 构建、回调处理、code 交换、token 刷新、
设备码流程的请求与轮询（含各错误分支）。
通过 mock aiohttp 与 cache 隔离网络与存储。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.mcp.auth.oauth_flows import (
    OAuthAuthorizationCodeHandler,
    OAuthDeviceCodeHandler,
)
from app.core.mcp.schemas import AuthConfig, AuthToken

_FUTURE = 4102444800  # 2100 年，远超当前时间戳


def _auth_code_config(**overrides):
    cfg = {
        "method": "oauth_authorization_code",
        "client_id": "cid",
        "client_secret": "secret",
        "authorization_endpoint": "https://auth/authorize",
        "token_endpoint": "https://auth/token",
        "redirect_uri": "http://localhost:8877/oauth/callback",
        "scopes": ["read", "write"],
    }
    cfg.update(overrides)
    return AuthConfig(**cfg)


def _device_config(**overrides):
    cfg = {
        "method": "oauth_device_code",
        "client_id": "cid",
        "device_authorization_endpoint": "https://auth/device",
        "token_endpoint": "https://auth/token",
        "scopes": ["read"],
    }
    cfg.update(overrides)
    return AuthConfig(**cfg)


class TestOAuthAuthorizationCode:
    def test_generate_pkce(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        verifier, challenge = h._generate_pkce()
        assert verifier
        assert challenge
        assert verifier != challenge

    def test_build_auth_url(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        h._state = "STATE123"
        url = h._build_auth_url("CHALLENGE")
        assert "client_id=cid" in url
        assert "code_challenge=CHALLENGE" in url
        assert "code_challenge_method=S256" in url
        assert "state=STATE123" in url
        assert "scope=read+write" in url

    def test_build_auth_url_no_scopes(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config(scopes=[]))
        h._state = "S"
        url = h._build_auth_url("C")
        assert "scope=" not in url

    async def test_handle_callback_success(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        h._state = "STATE123"
        h._pending_codes["STATE123"] = asyncio.get_running_loop().create_future()
        await h.handle_callback(
            "http://localhost:8877/oauth/callback?code=CODE1&state=STATE123"
        )
        assert h._pending_codes["STATE123"].done()

    async def test_handle_callback_error(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        with pytest.raises(RuntimeError, match="OAuth error"):
            await h.handle_callback("http://localhost/cb?error=access_denied")

    async def test_handle_callback_missing_code(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        with pytest.raises(ValueError, match="Missing code or state"):
            await h.handle_callback("http://localhost/cb?code=x")

    async def test_handle_callback_invalid_state(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        h._pending_codes = {}
        with pytest.raises(ValueError, match="Invalid state"):
            await h.handle_callback("http://localhost/cb?code=x&state=BAD")

    async def test_exchange_code(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        h._code_verifier = "VERIFIER"
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={
            "access_token": "AT", "token_type": "Bearer", "expires_in": 3600,
            "refresh_token": "RT", "scope": "read",
        })
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with patch("aiohttp.ClientSession", cls_mock):
            token = await h._exchange_code("CODE1")
        assert token.access_token == "AT"
        assert token.refresh_token == "RT"

    async def test_exchange_code_failure(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        h._code_verifier = "V"
        resp = MagicMock()
        resp.status = 400
        resp.text = AsyncMock(return_value="bad")
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with patch("aiohttp.ClientSession", cls_mock):
            with pytest.raises(RuntimeError, match="Token exchange failed"):
                await h._exchange_code("CODE1")

    async def test_refresh_success(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        old = AuthToken(access_token="old", refresh_token="RT", token_type="Bearer")
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"access_token": "new", "expires_in": 3600})
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with (
            patch("aiohttp.ClientSession", cls_mock),
            patch.object(h, "_store_token", new=AsyncMock()),
        ):
            token = await h.refresh(old)
        assert token.access_token == "new"
        assert token.refresh_token == "RT"  # 保留原 refresh token

    async def test_refresh_no_refresh_token(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        old = AuthToken(access_token="old")
        with pytest.raises(ValueError, match="No refresh token"):
            await h.refresh(old)

    async def test_authenticate_uses_stored_token(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        stored = AuthToken(access_token="stored", expires_in=_FUTURE)
        with patch.object(h, "load_stored_token", new=AsyncMock(return_value=stored)):
            token = await h.authenticate()
        assert token.access_token == "stored"

    async def test_store_and_load_token(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        token = AuthToken(access_token="AT", refresh_token="RT", token_type="Bearer")
        with patch("app.core.mcp.auth.oauth_flows.cache") as cache_mock:
            cache_mock.set = AsyncMock()
            await h._store_token(token)
            cache_mock.set.assert_awaited()
            assert cache_mock.set.await_count == 2  # token + refresh

    async def test_load_stored_token_none(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        with patch("app.core.mcp.auth.oauth_flows.cache") as cache_mock:
            cache_mock.get = AsyncMock(return_value=None)
            assert await h.load_stored_token() is None

    async def test_load_stored_token_valid(self):
        h = OAuthAuthorizationCodeHandler("srv", _auth_code_config())
        import json
        data = json.dumps({"access_token": "AT", "token_type": "Bearer", "expires_in": _FUTURE})
        with patch("app.core.mcp.auth.oauth_flows.cache") as cache_mock:
            cache_mock.get = AsyncMock(return_value=data)
            token = await h.load_stored_token()
        assert token.access_token == "AT"


class _AsyncRespCtx:
    """模拟 async with session.post(...) as resp: 的上下文。"""

    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


def _fake_aiohttp_session(post_handler):
    """构造 mock 的 aiohttp.ClientSession 链。

    ``async with aiohttp.ClientSession() as session:`` 中 body 的 session 是
    ``ClientSession.return_value.__aenter__.return_value``，post 挂在它上面。
    """
    cls_mock = MagicMock()
    session = MagicMock()
    session.post = post_handler
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    cls_mock.return_value = cm
    return cls_mock


class TestOAuthDeviceCode:
    async def test_request_device_code(self):
        h = OAuthDeviceCodeHandler("srv", _device_config(scopes=["read"]))
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"user_code": "UC", "verification_uri": "https://v", "device_code": "DC"})
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with patch("aiohttp.ClientSession", cls_mock):
            data = await h._request_device_code()
        assert data["device_code"] == "DC"

    async def test_request_device_code_failure(self):
        h = OAuthDeviceCodeHandler("srv", _device_config(scopes=["read"]))
        resp = MagicMock()
        resp.status = 500
        resp.text = AsyncMock(return_value="err")
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with patch("aiohttp.ClientSession", cls_mock):
            with pytest.raises(RuntimeError, match="Device code request failed"):
                await h._request_device_code()

    async def test_poll_success(self):
        h = OAuthDeviceCodeHandler("srv", _device_config())
        resp = MagicMock()
        resp.json = AsyncMock(return_value={"access_token": "AT", "expires_in": 3600})
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with (
            patch("aiohttp.ClientSession", cls_mock),
            patch("app.core.mcp.auth.oauth_flows.cache") as cache_mock,
        ):
            cache_mock.set = AsyncMock()
            token = await h._poll_for_token("DC", interval=0, expires_in=5)
        assert token.access_token == "AT"

    async def test_poll_authorization_pending_then_success(self):
        h = OAuthDeviceCodeHandler("srv", _device_config())
        # 第一次 pending，第二次成功

        calls = {"n": 0, "args": None}

        def _fake_post(*args, **kwargs):
            calls["args"] = (args, kwargs)
            calls["n"] += 1
            resp = MagicMock()
            if calls["n"] == 1:
                resp.json = AsyncMock(return_value={"error": "authorization_pending"})
            else:
                resp.json = AsyncMock(return_value={"access_token": "AT", "expires_in": 3600})
            return _AsyncRespCtx(resp)

        cls_mock = _fake_aiohttp_session(_fake_post)
        with (
            patch("aiohttp.ClientSession", cls_mock),
            patch("app.core.mcp.auth.oauth_flows.cache") as cache_mock,
        ):
            cache_mock.set = AsyncMock()
            token = await h._poll_for_token("DC", interval=0, expires_in=5)
        assert token.access_token == "AT"
        assert calls["n"] == 2

    async def test_poll_error_branches(self):
        from app.core.mcp.auth.oauth_flows import OAuthDeviceCodeHandler

        h = OAuthDeviceCodeHandler("srv", _device_config())
        cases = [
            ("expired_token", "Device code expired"),
            ("access_denied", "denied"),
            ("unknown_err", "OAuth error"),
        ]
        for error, pattern in cases:
            resp = MagicMock()
            resp.json = AsyncMock(return_value={"error": error})
            cls_mock = _fake_aiohttp_session(lambda *a, _r=resp, **k: _AsyncRespCtx(_r))
            with patch("aiohttp.ClientSession", cls_mock):
                with pytest.raises(RuntimeError, match=pattern):
                    await h._poll_for_token("DC", interval=0, expires_in=5)

    async def test_refresh_success(self):
        h = OAuthDeviceCodeHandler("srv", _device_config())
        old = AuthToken(access_token="old", refresh_token="RT", token_type="Bearer")
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value={"access_token": "new", "expires_in": 3600})
        cls_mock = _fake_aiohttp_session(lambda *a, **k: _AsyncRespCtx(resp))
        with (
            patch("aiohttp.ClientSession", cls_mock),
            patch("app.core.mcp.auth.oauth_flows.cache") as cache_mock,
        ):
            cache_mock.set = AsyncMock()
            token = await h.refresh(old)
        assert token.access_token == "new"
