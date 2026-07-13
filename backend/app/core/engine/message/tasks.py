"""
Mobile Sync Tasks — 异步投递消息到 MC（Worker 进程）。

WS 不可达时由 MessagePublisher 入队，Worker 消费后 HTTP→MC。
支持自动重试（@shared_task retries），避免 API 进程被 HTTP 阻塞。
"""

import logging

from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="engine.mobile_sync_http",
    retries=2,
    retry_delay=30,
)
async def mobile_sync_http_task(mobile_data: dict) -> None:
    """通过 HTTP 将消息推送到 MC（Mobile 兜底通道，Worker 进程执行）。"""
    from app.core.evocloud import evocloud_manager
    from app.core.identity import identity_service

    device_key = await identity_service.store.get_device_key() or ""
    thread_id = mobile_data.get("thread_id") or ""

    if not device_key:
        logger.warning("[MobileSyncTask] No device_key, skipping HTTP fallback")
        return

    try:
        resp = await evocloud_manager.api.sync_messages(
            device_key=device_key,
            thread_id=thread_id,
            messages=[mobile_data],
        )
        code = resp.get("code", -1) if isinstance(resp, dict) else -1
        if code == 0:
            logger.debug(
                "[MobileSyncTask] HTTP fallback success: seq=%s",
                mobile_data.get("sequence_number"),
            )
        else:
            logger.warning(
                "[MobileSyncTask] HTTP fallback failed: code=%s, resp=%s",
                code,
                str(resp)[:200],
            )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
        logger.warning("[MobileSyncTask] HTTP fallback error: %s", e)
        raise  # 触发 Huey 重试
