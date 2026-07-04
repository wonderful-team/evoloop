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
    from app.core.identity import identity_service
    from app.core.config import settings
    import httpx

    token = await identity_service.get_access_token()
    if not token:
        logger.warning("[MobileSyncTask] No token, skipping HTTP fallback")
        return

    try:
        url = f"{settings.MEMBER_CENTER_URL}/evolooplink/api/sync/messages"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json=mobile_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.is_success:
                logger.debug(
                    "[MobileSyncTask] HTTP fallback success: seq=%s",
                    mobile_data.get("sequence_number"),
                )
            else:
                logger.warning(
                    "[MobileSyncTask] HTTP fallback failed: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as e:
        logger.warning("[MobileSyncTask] HTTP fallback error: %s", e)
        raise  # 触发 Huey 重试
