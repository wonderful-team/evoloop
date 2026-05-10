#!/usr/bin/env python3
"""
模拟测试：验证 token 过期 + refresh_token 缺失时的死循环行为
"""
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["EMBEDDED_MODE"] = "true"


class FakeResponse:
    """模拟 httpx.Response"""
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


async def test_token_refresh_updates_cache():
    """测试刷新后新 token 是否正确写入缓存"""
    from app.core.identity import identity_service
    from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
    from app.core.evocloud.schemas import EvoCloudConfig

    await identity_service.logout()

    old_token = "old_access_token_123"
    refresh_token = "refresh_token_456"
    await identity_service.set_token(old_token, refresh_token)

    print(f"[Setup] access_token={await identity_service.get_access_token()!r}, refresh_token={await identity_service.get_refresh_token()!r}")

    config = EvoCloudConfig(api_url="http://test.local", ws_url="ws://test.local")
    client = EvoCloudHTTPClient(config)

    request_count = 0
    async def mock_httpx_request(self, method, url, **kwargs):
        nonlocal request_count
        request_count += 1
        if "/api/member/info" in url:
            params = kwargs.get("params", {})
            sent_token = params.get("token", "")
            if sent_token == old_token:
                return FakeResponse(200, {"code": -10010, "message": "TOKEN_EXPIRE"})
            elif sent_token == "new_access_token_789":
                return FakeResponse(200, {"code": 0, "data": {"member_id": 1, "username": "test"}})
            else:
                return FakeResponse(200, {"code": -10010, "message": "TOKEN_EXPIRE"})
        elif "/api/login/refreshToken" in url:
            return FakeResponse(200, {
                "code": 0,
                "data": {
                    "token": "new_access_token_789",
                    "refresh_token": "new_refresh_token_abc",
                },
            })
        return FakeResponse(200, {"code": 0})

    # Patch cache.lock to avoid distributed-lock contention in test environment
    from app.infrastructure.cache import cache
    mock_lock = MagicMock()
    mock_lock.acquire = AsyncMock(return_value=True)
    mock_lock.release = AsyncMock()

    with patch("httpx.AsyncClient.request", mock_httpx_request), \
         patch.object(cache, "lock", return_value=mock_lock):
        result = await client.get_user_info(token=old_token)
        print(f"[Result] get_user_info = {result}")

    new_access = await identity_service.get_access_token()
    new_refresh = await identity_service.get_refresh_token()
    print(f"[Cache] after refresh: access_token={new_access!r}, refresh_token={new_refresh!r}")
    assert new_access == "new_access_token_789"
    assert new_refresh == "new_refresh_token_abc"

    await identity_service.logout()
    print("\n✅ test_token_refresh_updates_cache PASSED")


async def test_missing_refresh_token_stops_retry():
    """测试没有 refresh_token 时，不会无限重试同一请求"""
    from app.core.identity import identity_service
    from app.core.evocloud.backends.http_client import EvoCloudHTTPClient
    from app.core.evocloud.schemas import EvoCloudConfig

    await identity_service.logout()

    old_token = "old_access_token_no_refresh"
    await identity_service.store.save_access_token(old_token)

    config = EvoCloudConfig(api_url="http://test.local", ws_url="ws://test.local")
    client = EvoCloudHTTPClient(config)

    request_count = 0
    async def mock_httpx_request(self, method, url, **kwargs):
        nonlocal request_count
        request_count += 1
        if "/api/member/info" in url:
            return FakeResponse(200, {"code": -10010, "message": "TOKEN_EXPIRE"})
        return FakeResponse(200, {"code": 0})

    with patch("httpx.AsyncClient.request", mock_httpx_request):
        result = await client.get_user_info(token=old_token)
        print(f"[Result] get_user_info (no refresh) = {result}")

    print(f"[RequestCount] total = {request_count}")
    assert request_count == 1, f"Expected 1 request, got {request_count}"
    assert result.code == -10010

    await identity_service.logout()
    print("\n✅ test_missing_refresh_token_stops_retry PASSED")


async def test_resolve_member_id_loop_when_no_refresh_token():
    """
    关键测试：模拟前端轮询，反复调用 resolve_member_id_from_token。
    当 access_token 过期且 refresh_token 缺失时，每次调用都会触发
    get_user_info() → -10010 → Missing Refresh Token。
    这是生产环境日志刷屏的根因。
    """
    from app.core.identity import identity_service
    from app.core.evocloud import evocloud_manager

    await identity_service.logout()

    old_token = "expired_token_xyz"
    await identity_service.store.save_access_token(old_token)
    # 不设置 refresh_token

    # 清理本地缓存
    from app.core.identity.service import _token_member_cache
    _token_member_cache.clear()

    request_count = 0
    async def mock_httpx_request(self, method, url, **kwargs):
        nonlocal request_count
        request_count += 1
        if "/api/member/info" in url:
            return FakeResponse(200, {"code": -10010, "message": "TOKEN_EXPIRE"})
        return FakeResponse(200, {"code": 0})

    with patch("httpx.AsyncClient.request", mock_httpx_request):
        # 模拟前端轮询 5 次
        for i in range(5):
            mid = await identity_service.resolve_member_id_from_token(old_token)
            print(f"[Poll #{i+1}] resolve_member_id_from_token('{old_token}') = {mid}, total_requests={request_count}")
            assert mid is None

    # 关键断言：每次轮询都会触发一次 /api/member/info 请求
    # 因为 resolve_member_id_from_token 失败时不缓存，所以每次都要请求 MC
    assert request_count == 5, f"Expected 5 requests (one per poll), got {request_count}"

    await identity_service.logout()
    _token_member_cache.clear()

    print("\n✅ test_resolve_member_id_loop_when_no_refresh_token PASSED")
    print("   ⚠️  这就是生产环境死循环的根因：前端轮询 + 无 refresh_token → 每次都要请求 MC")


async def test_resolve_member_id_with_successful_cache():
    """测试 resolve_member_id_from_token 成功时会缓存，不会重复请求"""
    from app.core.identity import identity_service

    await identity_service.logout()

    valid_token = "valid_token_abc"
    await identity_service.store.save_access_token(valid_token)

    from app.core.identity.service import _token_member_cache
    _token_member_cache.clear()

    request_count = 0
    async def mock_httpx_request(self, method, url, **kwargs):
        nonlocal request_count
        request_count += 1
        if "/api/member/info" in url:
            return FakeResponse(200, {"code": 0, "data": {"member_id": 42, "username": "test"}})
        return FakeResponse(200, {"code": 0})

    with patch("httpx.AsyncClient.request", mock_httpx_request):
        # 第一次：请求 MC
        mid1 = await identity_service.resolve_member_id_from_token(valid_token)
        assert mid1 == 42
        assert request_count == 1

        # 第二次：命中本地缓存，不再请求 MC
        mid2 = await identity_service.resolve_member_id_from_token(valid_token)
        assert mid2 == 42
        assert request_count == 1, f"Expected cache hit, but request_count={request_count}"

    await identity_service.logout()
    _token_member_cache.clear()

    print("\n✅ test_resolve_member_id_with_successful_cache PASSED")


async def test_frontend_polling_after_logout():
    """
    模拟前端在用户 logout 后仍继续轮询 /api/v1/member/me 的场景。
    logout 清除了所有 token，但前端没有停止轮询。
    """
    from app.core.identity import identity_service
    from app.core.evocloud import evocloud_manager

    # 先登录
    await identity_service.logout()
    old_token = "user_token_before_logout"
    refresh_token = "refresh_before_logout"
    await identity_service.set_token(old_token, refresh_token)

    from app.core.identity.service import _token_member_cache
    _token_member_cache.clear()

    request_count = 0
    async def mock_httpx_request(self, method, url, **kwargs):
        nonlocal request_count
        request_count += 1
        if "/api/member/info" in url:
            return FakeResponse(200, {"code": -10010, "message": "TOKEN_EXPIRE"})
        elif "/api/login/refreshToken" in url:
            return FakeResponse(200, {"code": -10010, "message": "REFRESH_TOKEN_INVALID"})
        return FakeResponse(200, {"code": 0})

    with patch("httpx.AsyncClient.request", mock_httpx_request):
        # 用户 logout（清除所有 token）
        await identity_service.logout()
        print(f"[Logout] access_token={await identity_service.get_access_token()!r}, refresh_token={await identity_service.get_refresh_token()!r}")

        # 但前端仍每 3 秒发送旧 token 轮询
        for i in range(3):
            mid = await identity_service.resolve_member_id_from_token(old_token)
            print(f"[Post-Logout Poll #{i+1}] resolve_member_id_from_token = {mid}, requests={request_count}")
            assert mid is None

    # logout 后没有 refresh_token，每次轮询都触发 Missing Refresh Token
    # 每次只发 1 个 /api/member/info 请求（不重试）
    assert request_count == 3, f"Expected 3 requests, got {request_count}"

    await identity_service.logout()
    _token_member_cache.clear()

    print("\n✅ test_frontend_polling_after_logout PASSED")
    print("   ⚠️  根因：前端 logout 后未停止轮询，导致每次请求都触发 -10010 + Missing Refresh Token")


async def main():
    print("=" * 70)
    print("Token Expire Loop Simulation Test")
    print("=" * 70)
    await test_token_refresh_updates_cache()
    await test_missing_refresh_token_stops_retry()
    await test_resolve_member_id_loop_when_no_refresh_token()
    await test_resolve_member_id_with_successful_cache()
    await test_frontend_polling_after_logout()
    print("\n" + "=" * 70)
    print("🎉 ALL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
