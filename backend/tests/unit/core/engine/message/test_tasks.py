"""Mobile sync tasks tests —— 验证 HTTP 兜底逻辑（evocloud sync_messages 版）"""
# 注意: @shared_task 在测试 conftest 中将 async 函数包装为 sync wrapper
# (内部使用 asyncio.run())，因此测试中直接调用即可，无需 await 或 pytest.mark.asyncio

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _patch_identity(device_key: str):
    mock_identity = MagicMock()
    mock_identity.store.get_device_key = AsyncMock(return_value=device_key)
    return patch("app.core.identity.identity_service", mock_identity)


def _patch_evocloud(resp=None, side_effect=None):
    mock_mgr = MagicMock()
    mock_mgr.api.sync_messages = AsyncMock(
        return_value=resp, side_effect=side_effect
    )
    return patch("app.core.evocloud.evocloud_manager", mock_mgr), mock_mgr


def test_success():
    """有 device_key 且 code=0 → 推送成功"""
    from app.core.engine.message.tasks import mobile_sync_http_task

    evo_patch, mock_mgr = _patch_evocloud(resp={"code": 0})
    with _patch_identity("dk-1"), evo_patch:
        mobile_sync_http_task(
            {"role": "human", "content": "hello", "thread_id": "t-1"}
        )

    mock_mgr.api.sync_messages.assert_awaited_once_with(
        device_key="dk-1",
        thread_id="t-1",
        messages=[{"role": "human", "content": "hello", "thread_id": "t-1"}],
    )


def test_no_device_key_skips():
    """无 device_key → 记 warning 并跳过，不调用云端"""
    from app.core.engine.message.tasks import mobile_sync_http_task

    evo_patch, mock_mgr = _patch_evocloud()
    with (
        _patch_identity(""),
        evo_patch,
        patch("app.core.engine.message.tasks.logger") as mock_logger,
    ):
        mobile_sync_http_task({"role": "human", "content": "hello"})

    mock_mgr.api.sync_messages.assert_not_called()
    mock_logger.warning.assert_any_call(
        "[MobileSyncTask] No device_key, skipping HTTP fallback"
    )


def test_failure_code_logs_warning():
    """云端返回 code!=0 → log warning，不抛异常（不回滚事务）"""
    from app.core.engine.message.tasks import mobile_sync_http_task

    evo_patch, _ = _patch_evocloud(resp={"code": 500, "msg": "boom"})
    with (
        _patch_identity("dk-1"),
        evo_patch,
        patch("app.core.engine.message.tasks.logger") as mock_logger,
    ):
        mobile_sync_http_task({"role": "human", "content": "hello"})

    mock_logger.warning.assert_any_call(
        "[MobileSyncTask] HTTP fallback failed: code=%s, resp=%s",
        500,
        "{'code': 500, 'msg': 'boom'}",
    )


def test_network_error_raises_for_retry():
    """网络异常 → 记 warning 并 propagate 以触发 Huey 重试"""
    from app.core.engine.message.tasks import mobile_sync_http_task

    evo_patch, _ = _patch_evocloud(side_effect=ConnectionError("Connection refused"))
    with _patch_identity("dk-1"), evo_patch:
        with pytest.raises(ConnectionError):
            mobile_sync_http_task({"role": "human", "content": "hello"})
