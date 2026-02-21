"""
Vision LLM Factory for multimodal capabilities.
Provides LLM instances configured for image understanding (GPT-4V, Claude Vision, etc.)
"""

import base64
import logging
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.infrastructure.llm.factory import LLMFactory

logger = logging.getLogger(__name__)


class VisionLLMFactory:
    """
    Factory for creating Vision-capable LLM instances.
    Supports GPT-4V, Claude 3, and other multimodal models.
    """

    # Known vision-capable models
    VISION_MODELS = {
        "openai": [
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4-vision-preview",
            "gpt-4o-mini"
        ],
        "anthropic": [
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3-5-sonnet",
        ],
    }

    @staticmethod
    def create_vision_llm(
        model_name: str | None = None, temperature: float = 0.3, max_tokens: int = 4096
    ) -> BaseChatModel:
        """
        Create a Vision-capable LLM instance using the core LLMFactory.
        """
        from app.infrastructure.config.service import SystemConfigService

        # Fetch dynamic config for vision specifically
        db_vision_model = SystemConfigService.get_value("VISION_MODEL")

        # Priority: explicit arg > DB Vision > Default
        final_model = model_name or db_vision_model or "gpt-4o"

        # OpenRouter Logic: Ensure prefix if using OpenRouter
        if "openrouter.ai" in (settings.OPENAI_BASE_URL or ""):
            if "/" not in final_model:
                final_model = f"openai/{final_model}"

        logger.info(f"Creating Vision LLM - Model: {final_model}")

        # Use the central LLMFactory to get provider-specific adapters (Anthropic, Moonshot, etc.)
        return LLMFactory.create_llm(
            model_name=final_model,
            temperature=temperature
        )

    @staticmethod
    def encode_image(image_path: str, max_size: int = 2048, quality: int = 85) -> str:
        """Encode image file to base64 string, compressing it if it's too large."""
        from PIL import Image
        from io import BytesIO

        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            with Image.open(path) as img:
                # Convert to RGB if necessary (e.g. RGBA pngs)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Resize if larger than max_size
                if max(img.size) > max_size:
                    ratio = max_size / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Save to buffer as JPEG to reduce base64 size
                buffered = BytesIO()
                img.save(buffered, format="JPEG", quality=quality)
                return base64.b64encode(buffered.getvalue()).decode("utf-8")
                
        except ImportError:
            logger.warning("Pillow not installed, falling back to uncompressed base64 encoding")
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to compress image {image_path}, falling back to raw: {e}")
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

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
    def create_image_message(
        image_path: str, prompt: str = "Describe this image in detail."
    ) -> HumanMessage:
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

        return HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": prompt},
            ]
        )

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
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{base64_image}"},
                }
            )

        content.append({"type": "text", "text": prompt})

        return HumanMessage(content=content)


# Convenience function
def get_vision_llm(model_name: str | None = None, **kwargs) -> BaseChatModel:
    """Get a default Vision LLM instance."""
    return VisionLLMFactory.create_vision_llm(model_name=model_name, **kwargs)
