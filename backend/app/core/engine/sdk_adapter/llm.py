"""OpenHands SDK LLM construction for the EvoCloud execution context."""

from __future__ import annotations

import warnings
from typing import Any

from app.core.config import settings
from app.core.context.manager import EvoContext
from app.core.engine.sdk_adapter.mock_llm import MOCK_MODEL, install, mock_enabled

# Gateway 模型名不在 litellm 价目表内；成本计量走 EvoCloud 侧，SDK 的本地
# 成本告警无消费者。窄过滤这一条 SDK telemetry 警告，避免每轮刷屏。
warnings.filterwarnings(
    "ignore",
    message=r"Cost calculation failed.*",
    category=UserWarning,
)
# bash/终端工具每次创建子进程都 fork；lancedb 在 import 时注册 before-fork
# 警告，但子进程 exec 后变成 shell、不继承 lance 状态——fork-safety 警告
# 在此场景为误报性噪音，同样窄过滤。
warnings.filterwarnings(
    "ignore",
    message=r"lance is not fork-safe.*",
    category=UserWarning,
)


async def create_sdk_llm(ctx: EvoContext, config: dict[str, Any]):
    """Build the SDK LLM without changing the existing gateway contract.

    EvoCloud Gateway is an OpenAI-compatible endpoint. The SDK transport is
    LiteLLM, which refuses provider-less model names
    (``litellm.BadRequestError: LLM Provider NOT provided`` — verified against
    the real gateway), so every model is prefixed ``openai/`` to force the
    OpenAI-compatible transport against our ``base_url``; LiteLLM strips the
    prefix and the gateway receives the bare name exactly like the legacy
    OpenAI client path.
    """

    from openhands.sdk import LLM

    max_input_tokens = settings.SDK_LLM_MAX_INPUT_TOKENS or None

    if mock_enabled():
        install()
        configurable = config.get("configurable") or {}
        model = configurable.get("model") or ctx.active_model or ""
        return LLM(
            model=f"openai/{model}" if model else MOCK_MODEL,
            api_key="mock",
            base_url="http://127.0.0.1:9",
            temperature=0.7,
            num_retries=2,
            stream=True,
            max_input_tokens=max_input_tokens,
        )

    configurable = config.get("configurable") or {}

    from app.core.evocloud import evocloud_manager

    token = ctx.token or await evocloud_manager.get_token() or ""
    gateway_url = evocloud_manager.api.root_url if evocloud_manager.api else ""
    if not gateway_url:
        raise ValueError("EvoLoop Gateway URL not configured")

    # Custom LLM mode (LLM_CONFIG_TYPE=custom) must honor the DB-configured
    # endpoint, mirroring the LLMFactory contract; otherwise every request
    # would be hijacked to the EvoLoop Gateway regardless of config.
    from app.infrastructure.config.service import SystemConfigService

    config_type = SystemConfigService.get_value("LLM_CONFIG_TYPE", "platform")
    base_url = ""
    api_key = token
    if config_type == "custom":
        base_url = SystemConfigService.get_value("LLM_BASE_URL") or ""
        api_key = SystemConfigService.get_value("LLM_API_KEY") or token
        if not base_url:
            raise ValueError("Custom LLM mode requires LLM_BASE_URL")
    else:
        base_url = f"{gateway_url}/gateway/v1"

    # The gateway assigns its default model when the model field is EMPTY
    # (legacy AdaptiveChatOpenAI sends model="" verbatim). LiteLLM needs a
    # provider prefix, so "openai/" alone yields an empty model name on the
    # wire — same contract as the legacy OpenAI client path.
    model = configurable.get("model") or ctx.active_model or ""
    return LLM(
        model=f"openai/{model}",
        api_key=api_key,
        base_url=base_url,
        temperature=0.7,
        num_retries=2,
        stream=True,
        max_input_tokens=max_input_tokens,
    )
