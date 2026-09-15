"""
Vision LLM Factory for multimodal capabilities.
Provides LLM instances configured for image understanding (GPT-4V, Claude Vision, etc.)
"""
import base64
import logging
from pathlib import Path
from typing import Any

from app.core.engine.message.native_classes import HumanMessage
from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.schemas import LLMConfig
from app.utils.http import is_http_url

logger = logging.getLogger(__name__)


class VisionLLMFactory:
    """
    Factory for creating Vision-capable LLM instances.
    Supports GPT-4V, Claude 3, and other multimodal models.
    """

    @staticmethod
    async def create_vision_llm_async(
        model_name: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        provider_type: str | None = None,
    ) -> Any:
        """
        Async version of create_vision_llm.
        Use this when already inside an async context to avoid thread overhead.
        """
        from app.infrastructure.config.service import SystemConfigService

        db_vision_model = SystemConfigService.get_value("VISION_MODEL")
        final_model = model_name or db_vision_model

        from app.infrastructure.llm.platform_service import llm_platform_service

        # DB 配置可能指向纯文本 chat 模型（历史遗留），发图片过去只会得到
        # "看不到图"的幻觉回复——校验目录标记，不支持视觉则视为未配置。
        if final_model and not model_name:
            configured = llm_platform_service.get_model_by_id(final_model)
            if configured is not None and not configured.supports_vision:
                logger.warning(
                    "[VisionLLMFactory] VISION_MODEL=%s is not a vision model "
                    "per the platform catalog; ignoring it",
                    final_model,
                )
                final_model = None

        # 未显式指定时，从平台目录自动选择支持视觉的模型；
        # 找不到则明确报错——绝不能 fallback 到纯文本 chat 模型
        #（那会导致模型"看不到"图片却编造分析结果）。
        if not final_model:
            vision_models = [
                m
                for m in llm_platform_service.get_cached_models()
                if m.supports_vision
            ]
            if vision_models:
                final_model = vision_models[0].model_id
                logger.info(
                    "[VisionLLMFactory] auto-selected vision model: %s", final_model
                )
            else:
                raise ValueError(
                    "no vision model available: VISION_MODEL is not configured "
                    "and the platform catalog has no model with supports_vision"
                )

        vision_base_url = base_url or SystemConfigService.get_value("VISION_BASE_URL")
        vision_api_key = api_key or SystemConfigService.get_value("VISION_API_KEY")
        vision_provider = provider_type or SystemConfigService.get_value("VISION_PROVIDER_TYPE")

        logger.info(
            f"Creating Vision LLM (async) - Model: {final_model}, "
            f"Base URL: {vision_base_url or '(platform/gateway)'}, "
            f"Provider: {vision_provider or '(auto)'}"
        )

        config = LLMConfig(
            model_name=final_model,
            temperature=temperature,
            base_url=vision_base_url,
            api_key=vision_api_key,
            provider_type=vision_provider,
        )
        return await LLMFactory.create_llm(config)

    @staticmethod
    def encode_image(image_path: str) -> str:
        """Encode image file to base64 string without any compression or resizing."""
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except OSError as e:
            logger.exception(f"Failed to encode image {image_path}: {e}")
            raise

    @staticmethod
    def get_image_media_type(image_path: str) -> str:
        """Get MIME type from image extension."""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/png")

    @staticmethod
    def create_image_message(image_path: str, prompt: str = "Describe this image in detail.") -> HumanMessage:
        """
        Create a HumanMessage with image content for Vision LLM.

        Args:
            image_path: Path to the image file
            prompt: Text prompt to accompany the image

        Returns:
            HumanMessage with multimodal content
        """
        if is_http_url(image_path):
            image_url = image_path
        else:
            base64_image = VisionLLMFactory.encode_image(image_path)
            media_type = VisionLLMFactory.get_image_media_type(image_path)
            image_url = f"data:{media_type};base64,{base64_image}"

        return HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": prompt},
        ])


# Convenience functions


async def get_vision_llm_async(model_name: str | None = None, **kwargs) -> Any:
    """Get a default Vision LLM instance (async). Use inside async contexts."""
    return await VisionLLMFactory.create_vision_llm_async(model_name=model_name, **kwargs)
