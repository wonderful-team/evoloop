"""
Generation client factory for image/video generation.

提供统一的 OpenAI 标准生成客户端（images/videos API），复用 LLMFactory 的
``EvoCloudPlatformAuth`` 网关鉴权（token 自动注入 + 401 自动刷新），与
聊天 / vision 分析链路保持一致，避免在工具层手写 token 逻辑。
"""

import logging
from typing import Any

from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


def _gateway_base_url() -> str:
    """Return the gateway OpenAI-compatible base URL, or "" if not configured."""
    gateway_url = evocloud_manager.api.root_url if evocloud_manager.api else ""
    if not gateway_url:
        return ""
    return f"{gateway_url}/gateway/v1"


def create_generation_client() -> Any:
    """
    Create a standard OpenAI AsyncOpenAI client pointed at the gateway.

    Uses the shared loop-bound httpx client with ``EvoCloudPlatformAuth`` so the
    request carries the latest access token and auto-refreshes on 401. No
    api_key is passed — the auth flow injects it at request time.

    Returns:
        ``openai.AsyncOpenAI`` instance bound to the gateway.

    Raises:
        ValueError: if the EvoLoop Gateway URL is not configured.
    """
    base_url = _gateway_base_url()
    if not base_url:
        raise ValueError("EvoLoop Gateway URL not configured")

    import openai

    from app.infrastructure.llm.factory import HTTP_CLIENT_POOL

    return openai.AsyncOpenAI(
        base_url=base_url,
        # api_key 为占位：EvoCloudPlatformAuth（HTTP_CLIENT_POOL 的 httpx.Auth）会在
        # 请求时用 evocloud_manager.get_token() 覆盖 Authorization header，并处理 401 刷新。
        api_key="evoloop-gateway",
        http_client=HTTP_CLIENT_POOL.get(),
        timeout=300.0,
    )


def is_gateway_configured() -> bool:
    """Whether the EvoLoop Gateway is configured (usable for generation)."""
    return bool(_gateway_base_url())
