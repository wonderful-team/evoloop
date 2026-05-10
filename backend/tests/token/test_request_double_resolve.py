#!/usr/bin/env python3
"""
端到端模拟测试：验证一次前端请求如何触发两次 MC /api/member/info 调用

生产环境死循环根因：
- 前端每 3 秒轮询（useProjectStatus / ActivityTab）
- 每次请求带过期 token
- ContextMiddleware + deps.py 各自调用 resolve_member_id_from_token
- 失败结果不缓存，每次都请求 MC /api/member/info
- 无 refresh_token 时每次都会打印 "Missing Refresh Token"
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["EMBEDDED_MODE"] = "true"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


async def _setup_mock_evocloud():
    """初始化 evocloud_manager 并替换其 httpx client"""
    from app.core.evocloud import evocloud_manager
    from app.core.evocloud.schemas import EvoCloudConfig

    if not evocloud_manager._initialized:
        config = EvoCloudConfig(api_url="http://test.local", ws_url="ws://test.local")
        evocloud_manager.initialize(config)

    api = evocloud_manager.api

    class MockClient:
        def __init__(self):
            self.request_log = []

        async def request(self, method, url, **kwargs):
            self.request_log.append({"method": method, "url": url, "kwargs": kwargs})
            if "/api/member/info" in url:
                return FakeResponse(200, {"code": -10010, "message": "TOKEN_EXPIRE"})
            if "/api/login/refreshToken" in url:
                return FakeResponse(200, {"code": 0, "data": {"token": "new_mock_token"}})
            return FakeResponse(200, {"code": 0})

        @property
        def is_closed(self):
            return False

        async def aclose(self):
            pass

    mock_client = MockClient()
    api._client = mock_client
    return mock_client


async def test_single_request_triggers_two_member_info_calls():
    """
    核心测试：一次前端请求 → 后端两次 /api/member/info
    """
    from fastapi import FastAPI, Depends
    from httpx import AsyncClient, ASGITransport
    from app.core.identity import identity_service
    from app.core.identity.service import _token_member_cache
    from app.core.context.middleware import ContextMiddleware
    from app.api.deps import get_current_user, CurrentUser

    await identity_service.logout()
    expired_token = "expired_token_for_test"
    await identity_service.store.save_access_token(expired_token)
    # 不设置 refresh_token → Missing Refresh Token
    _token_member_cache.clear()

    app = FastAPI()
    app.add_middleware(ContextMiddleware)

    @app.get("/api/v1/projects/{project_id}/status")
    async def get_project_status(project_id: int, user: CurrentUser):
        return {"status": "ok", "project_id": project_id, "user_id": user.id}

    mock_client = await _setup_mock_evocloud()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/projects/123/status",
            headers={"Authorization": f"Bearer {expired_token}"}
        )

    print(f"[HTTP Response] status={response.status_code}, body={response.text}")
    print(f"[Request Log] total MC requests = {len(mock_client.request_log)}")
    for i, req in enumerate(mock_client.request_log):
        print(f"  #{i+1}: {req['method']} {req['url']}")

    # 1. 返回 401
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    # 2. 两次 /api/member.info（ContextMiddleware + deps.py）
    member_info_calls = [r for r in mock_client.request_log if "/api/member/info" in r["url"]]
    assert len(member_info_calls) == 2, f"Expected 2 /api/member/info, got {len(member_info_calls)}"

    # 3. 无 refresh_token，不会发 refreshToken 请求
    refresh_calls = [r for r in mock_client.request_log if "/api/login/refreshToken" in r["url"]]
    assert len(refresh_calls) == 0, f"Expected 0 refreshToken, got {len(refresh_calls)}"

    await identity_service.logout()
    _token_member_cache.clear()

    print("\n✅ test_single_request_triggers_two_member_info_calls PASSED")


async def test_frontend_polling_simulation():
    """模拟前端每 3 秒轮询 3 次（无 refresh_token）"""
    from fastapi import FastAPI, Depends
    from httpx import AsyncClient, ASGITransport
    from app.core.identity import identity_service
    from app.core.identity.service import _token_member_cache
    from app.core.context.middleware import ContextMiddleware
    from app.api.deps import get_current_user, CurrentUser

    await identity_service.logout()
    expired_token = "expired_token_polling"
    await identity_service.store.save_access_token(expired_token)
    _token_member_cache.clear()

    app = FastAPI()
    app.add_middleware(ContextMiddleware)

    @app.get("/api/v1/projects/{project_id}/status")
    async def get_project_status(project_id: int, user: CurrentUser):
        return {"status": "ok"}

    mock_client = await _setup_mock_evocloud()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for i in range(3):
            resp = await client.get(
                "/api/v1/projects/123/status",
                headers={"Authorization": f"Bearer {expired_token}"}
            )
            print(f"[Poll #{i+1}] status={resp.status_code}")

    member_info_calls = [r for r in mock_client.request_log if "/api/member/info" in r["url"]]
    refresh_calls = [r for r in mock_client.request_log if "/api/login/refreshToken" in r["url"]]

    print(f"\n[Total] /api/member/info: {len(member_info_calls)}, refreshToken: {len(refresh_calls)}")
    assert len(member_info_calls) == 6, f"Expected 6, got {len(member_info_calls)}"
    assert len(refresh_calls) == 0, f"Expected 0, got {len(refresh_calls)}"

    await identity_service.logout()
    _token_member_cache.clear()

    print("\n✅ test_frontend_polling_simulation PASSED")
    print("   ⚠️  前端 3 次轮询 → 后端 6 次 /api/member/info → 6 次 'Missing Refresh Token' 日志")


async def main():
    print("=" * 70)
    print("Request Double Resolve Simulation Test")
    print("=" * 70)
    await test_single_request_triggers_two_member_info_calls()
    print()
    await test_frontend_polling_simulation()
    print("\n" + "=" * 70)
    print("🎉 ALL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
