import logging
import os

from langchain_core.tools import tool

from app.core.llm.vision import VisionLLMFactory, get_vision_llm

logger = logging.getLogger(__name__)


@tool
async def analyze_image(image_source: str, question: str = "Describe this image in detail.") -> str:
    """
    Analyze an image using a multimodal LLM (GPT-4o) to answer questions about it.
    
    Args:
        image_source: The absolute path to a local image file OR a public image URL.
        question: The question or instruction about the image (e.g., "What is in this image?", "Describe the layout bug").
        
    Returns:
        A text description or answer derived from the image analysis.
    """
    try:
        # Validate local file existence if not URL
        if not (image_source.startswith("http://") or image_source.startswith("https://")):
            if not os.path.exists(image_source):
                return f"Error: Image file not found at: {image_source}"

        from app.core.config import settings

        # Determine model name based on provider
        model = "gpt-4o"
        if "openrouter.ai" in settings.OPENAI_BASE_URL:
            model = "openai/gpt-4o"

        # Get Vision LLM
        llm = get_vision_llm(model_name=model)

        # Create Message
        message = VisionLLMFactory.create_image_message(image_source, question)

        # Invoke
        response = await llm.ainvoke([message])

        logger.info(f"Analyzed image: {image_source}")
        return response.content

    except Exception as e:
        error_msg = str(e)
        if "model_not_found" in error_msg:
            return f"Error: Vision model '{model}' is not available with your current API Key/Provider. Please check your credits or model access."

        logger.error(f"Error analyzing image: {e}")
        return f"Error analyzing image: {error_msg}"
