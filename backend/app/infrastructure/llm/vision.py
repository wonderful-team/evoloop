"""
Vision LLM Factory for multimodal capabilities.
Provides LLM instances configured for image understanding (GPT-4V, Claude Vision, etc.)
"""

import base64
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.infrastructure.llm.factory import LLMFactory
from app.infrastructure.schemas import LLMConfig

logger = logging.getLogger(__name__)


class VisionLLMFactory:
    """
    Factory for creating Vision-capable LLM instances.
    Supports GPT-4V, Claude 3, and other multimodal models.
    """

    @staticmethod
    def create_vision_llm(
        model_name: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        provider_type: str | None = None,
    ) -> BaseChatModel:
        """
        Create a Vision-capable LLM instance using the core LLMFactory.
        
        Supports independent connection configuration for Vision (e.g., local VLM)
        while LLM uses a different remote endpoint.
        
        This is a synchronous wrapper that works in both sync and async contexts.
        """
        import concurrent.futures
        from app.infrastructure.config.service import SystemConfigService

        # Fetch dynamic config for vision specifically
        db_vision_model = SystemConfigService.get_value("VISION_MODEL")

        # Priority: explicit arg > DB Vision > Default
        final_model = model_name or db_vision_model

        # Fetch independent Vision connection config if no explicit overrides
        vision_base_url = base_url or SystemConfigService.get_value("VISION_BASE_URL")
        vision_api_key = api_key or SystemConfigService.get_value("VISION_API_KEY")
        vision_provider = provider_type or SystemConfigService.get_value("VISION_PROVIDER_TYPE")

        logger.info(
            f"Creating Vision LLM - Model: {final_model}, "
            f"Base URL: {vision_base_url or '(platform/gateway)'}, "
            f"Provider: {vision_provider or '(auto)'}"
        )

        # Build coroutine using the central LLMFactory
        config = LLMConfig(
            model_name=final_model,
            temperature=temperature,
            base_url=vision_base_url,
            api_key=vision_api_key,
            provider_type=vision_provider,
        )
        coro = LLMFactory.create_llm(config)

        # Execute the async factory synchronously, handling both sync and async contexts
        try:
            import asyncio
            return asyncio.run(coro)
        except RuntimeError:
            # Inside a running event loop (e.g., FastAPI request handler).
            # Run in a separate thread with its own event loop to avoid conflicts.
            def _run_coro_in_new_loop(c):
                import asyncio
                return asyncio.run(c)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(_run_coro_in_new_loop, coro).result()

    @staticmethod
    async def create_vision_llm_async(
        model_name: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        provider_type: str | None = None,
    ) -> BaseChatModel:
        """
        Async version of create_vision_llm.
        Use this when already inside an async context to avoid thread overhead.
        """
        from app.infrastructure.config.service import SystemConfigService

        db_vision_model = SystemConfigService.get_value("VISION_MODEL")
        final_model = model_name or db_vision_model

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
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
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
        if image_path.startswith("http://") or image_path.startswith("https://"):
            image_url = image_path
        else:
            base64_image = VisionLLMFactory.encode_image(image_path)
            media_type = VisionLLMFactory.get_image_media_type(image_path)
            image_url = f"data:{media_type};base64,{base64_image}"

        return HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": prompt},
        ])

    @staticmethod
    def create_multi_image_message(image_paths: list[str], prompt: str) -> HumanMessage:
        """
        Create a HumanMessage with multiple images for comparison/analysis.

        Args:
            image_paths: List of paths to image files
            prompt: Text prompt for multi-image analysis

        Returns:
            HumanMessage with multimodal content
        """
        content = []

        for path in image_paths:
            base64_image = VisionLLMFactory.encode_image(path)
            media_type = VisionLLMFactory.get_image_media_type(path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{base64_image}"},
            })

        content.append({"type": "text", "text": prompt})

        return HumanMessage(content=content)


# Convenience functions
def get_vision_llm(model_name: str | None = None, **kwargs) -> BaseChatModel:
    """Get a default Vision LLM instance (sync)."""
    return VisionLLMFactory.create_vision_llm(model_name=model_name, **kwargs)


async def get_vision_llm_async(model_name: str | None = None, **kwargs) -> BaseChatModel:
    """Get a default Vision LLM instance (async). Use inside async contexts."""
    return await VisionLLMFactory.create_vision_llm_async(model_name=model_name, **kwargs)
