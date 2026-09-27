"""复现：为何 MC 设置 token 有效期"无限"仍被登出。

根因假设（已在调用链上定位）：
  前端 access_token 是否有效，取决于 ``identity_service.resolve_member_id_from_token``
  能否解析出 member_id。该函数：
    1. 命中缓存 ``evoloop:token_mid:<token>`` → 直接返回（2 分钟 TTL 内 OK）
    2. 缓存错过 → live 打 MC ``get_user_info(token)``；只要结果 ``code != 0``
       或抛异常，就返回 ``None``（不做任何 refresh / 缓存降级）。

  ``get_current_user`` 拿到 ``None`` 就抛 401 → 前端删 token 跳登录 = 登出。

  因此：即便 MC 里 access_token 有效期是"无限"，只要 2 分钟缓存过期后那一次
  MC 校验恰好失败（网络抖动 / MC 返回非零 / refresh_token 未持久化），
  就会被打成 401 登出。本测试用可控 mock 复现该"无限 token 仍被登出"的机制。
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.evocloud.manager import evocloud_manager
from app.core.identity import constants as identity_constants
from app.core.identity import service as identity_service_mod
from app.core.identity.service import IdentityService
from app.infrastructure.cache import cache

TOKEN = "infinite-token-abc"
MID = 42


@contextlib.contextmanager
def _patch_api(api: MagicMock):
    """把 EvoCloudManager.api 的底层 _api_pool 指向给定 mock（api 是只读 property）。

    同时置 _initialized=True 防止 api property 访问时重新初始化替换掉打桩的池。
    """
    with (
        patch.object(evocloud_manager, "_initialized", True),
        patch.object(
            evocloud_manager,
            "_api_pool",
            MagicMock(get=lambda: api),
        ),
    ):
        yield


async def test_cache_hit_does_not_call_mc():
    """缓存命中：不触发 MC 调用，任意有效期都能解析（正常路径）。"""
    svc = IdentityService()
    api = MagicMock()
    api.get_user_info = AsyncMock()
    with (
        patch.object(svc, "_pending_resolutions", {}),
        patch.object(cache, "get", AsyncMock(return_value=str(MID))),
        _patch_api(api),
    ):
        mid = await svc.resolve_member_id_from_token(TOKEN)

    assert mid == MID
    api.get_user_info.assert_not_awaited()


async def test_cache_miss_mc_success_recaches():
    """缓存错过 + MC 成功：解析成功并回填缓存（正常路径）。"""
    svc = IdentityService()
    api = MagicMock()
    mc_ok = {"code": 0, "data": {"member_id": MID, "nickname": "a"}}
    with (
        patch.object(svc, "_pending_resolutions", {}),
        patch.object(cache, "get", AsyncMock(return_value=None)),
        patch.object(cache, "set", AsyncMock(return_value=True)) as cset,
        _patch_api(api),
    ):
        api.get_user_info = AsyncMock(return_value=mc_ok)
        mid = await svc.resolve_member_id_from_token(TOKEN)

    assert mid == MID
    cset.assert_awaited()
    first_call_args = cset.await_args_list[0].args
    assert first_call_args[0] == f"evoloop:token_mid:{TOKEN}"
    assert cset.await_args_list[0].kwargs["ex"] == identity_constants.TOKEN_CACHE_TTL


@pytest.mark.parametrize(
    "mc_result",
    [
        {"code": -10009, "message": "TOKEN_EXPIRE"},  # MC 判定 token 过期
        {"code": -1, "message": "network error"},  # 临时性失败（非明确的过期）
        {"code": 500, "message": "upstream error"},
    ],
)
async def test_cache_miss_mc_failure_causes_none_then_401(mc_result):
    """核心复现：缓存错过 + MC 校验失败 → resolve 返回 None → get_current_user 抛 401。

    token 本身在 MC 可能是"无限"的，但只要这次 live 校验返回非零/抛出，
    就会被判死成 401 —— 这就是"无限期 token 仍频繁登出"的机制。
    """
    svc = IdentityService()
    api = MagicMock()
    with (
        patch.object(svc, "_pending_resolutions", {}),
        patch.object(cache, "get", AsyncMock(return_value=None)),
        patch.object(cache, "set", AsyncMock(return_value=True)),
        _patch_api(api),
    ):
        api.get_user_info = AsyncMock(return_value=mc_result)
        mid = await svc.resolve_member_id_from_token(TOKEN)

    assert mid is None

    from fastapi import HTTPException

    from app.api.deps import get_current_user

    class _Req:
        state = type("S", (), {})()

    req = _Req()
    api_fail = MagicMock()
    api_fail.get_user_info = AsyncMock(side_effect=RuntimeError("conn reset"))
    svc2 = IdentityService()
    svc2._pending_resolutions = {}
    with (
        patch.object(identity_service_mod, "identity_service", svc2),
        patch("app.api.deps.identity_service", svc2),
        patch("app.api.deps.settings.MULTI_TENANT_MODE", True),
        patch("app.infrastructure.cache.cache.get", AsyncMock(return_value=None)),
        _patch_api(api_fail),
    ):
        with pytest.raises(HTTPException) as einfo:
            await get_current_user(req, token=TOKEN)
        assert einfo.value.status_code == 401


async def test_cache_miss_mc_exception_also_logs_out():
    """MC 调用抛异常（网络抖动）同样返回 None → 401。"""
    svc = IdentityService()
    api = MagicMock()
    with (
        patch.object(svc, "_pending_resolutions", {}),
        patch.object(cache, "get", AsyncMock(return_value=None)),
        _patch_api(api),
    ):
        api.get_user_info = AsyncMock(side_effect=RuntimeError("conn reset"))
        mid = await svc.resolve_member_id_from_token(TOKEN)

    assert mid is None


async def test_cache_miss_mc_success_but_no_member_id_returns_none():
    """MC 返回 code=0 但没有 member_id 字段，也会被判为无效。"""
    svc = IdentityService()
    api = MagicMock()
    with (
        patch.object(svc, "_pending_resolutions", {}),
        patch.object(cache, "get", AsyncMock(return_value=None)),
        _patch_api(api),
    ):
        api.get_user_info = AsyncMock(return_value={"code": 0, "data": {}})
        mid = await svc.resolve_member_id_from_token(TOKEN)

    assert mid is None
