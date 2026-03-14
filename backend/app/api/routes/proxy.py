"""AI Service Proxy - Client delegates all AI calls to Server.

This module provides unified proxy endpoints for:
- LLM (chat completions)
- Vision (multimodal)
- Embeddings

Client should configure:
  LLM_BASE_URL = http://server:8000/api/v1/proxy
"""

import logging
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proxy", tags=["proxy"])


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict] | None = None
    tool_choice: str | None = None


class EmbeddingRequest(BaseModel):
    """OpenAI-compatible embedding request."""
    model: str
    input: str | list[str]
    encoding_format: str = "float"


async def _get_llm_config():
    """Get LLM config from server settings."""
    return {
        "provider": getattr(settings, 'LLM_PROVIDER', 'openai'),
        "base_url": getattr(settings, 'LLM_BASE_URL', settings.OPENAI_BASE_URL),
        "api_key": getattr(settings, 'LLM_API_KEY', settings.OPENAI_API_KEY),
        "model": getattr(settings, 'LLM_MODEL', settings.OPENAI_MODEL_NAME),
    }


async def _get_embedding_config():
    """Get Embedding config from server settings."""
    return {
        "provider": settings.EMBEDDING_PROVIDER,
        "base_url": settings.EMBEDDING_BASE_URL or settings.OPENAI_BASE_URL,
        "api_key": settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY,
        "model": settings.EMBEDDING_MODEL_NAME,
    }


@router.post("/chat/completions", dependencies=[Depends(get_current_user)])
async def proxy_chat_completions(request: ChatCompletionRequest):
    """
    Proxy LLM chat completions to configured provider.

    Client should use this endpoint as base_url for OpenAI client.
    """
    config = await _get_llm_config()

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = request.model_dump(exclude_none=True)

    # Use server's configured model if not specified
    if not payload.get("model"):
        payload["model"] = config["model"]

    url = f"{config['base_url']}/chat/completions"

    try:
        async with httpx.AsyncClient() as client:
            if request.stream:
                # Streaming response
                async def stream_generator() -> AsyncGenerator[str, None]:
                    async with client.stream(
                        "POST", url, headers=headers, json=payload, timeout=300.0
                    ) as response:
                        if response.status_code != 200:
                            error = await response.aread()
                            logger.error(f"LLM streaming error: {error}")
                            yield f"data: {{\"error\": \"LLM request failed\"}}\n\n"
                            return

                        async for line in response.aiter_lines():
                            if line:
                                yield f"{line}\n\n"

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )
            else:
                # Non-streaming response
                response = await client.post(
                    url, headers=headers, json=payload, timeout=300.0
                )
                response.raise_for_status()
                return response.json()

    except httpx.HTTPError as e:
        logger.error(f"LLM proxy request failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM service error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in LLM proxy: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/embeddings", dependencies=[Depends(get_current_user)])
async def proxy_embeddings(request: EmbeddingRequest):
    """
    Proxy embedding requests to configured provider.

    Client should use this endpoint for embedding calls.
    """
    config = await _get_embedding_config()

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = request.model_dump(exclude_none=True)
    if not payload.get("model"):
        payload["model"] = config["model"]

    url = f"{config['base_url']}/embeddings"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=payload, timeout=60.0
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        logger.error(f"Embedding proxy request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Embedding service error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in embedding proxy: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/vision", dependencies=[Depends(get_current_user)])
async def proxy_vision(request: ChatCompletionRequest):
    """
    Proxy Vision/multimodal requests to configured provider.

    Uses VISION_MODEL from server config if available.
    """
    config = await _get_llm_config()
    vision_model = getattr(settings, 'VISION_MODEL', config["model"])

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    payload = request.model_dump(exclude_none=True)
    payload["model"] = vision_model  # Use vision-specific model

    url = f"{config['base_url']}/chat/completions"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, headers=headers, json=payload, timeout=120.0
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        logger.error(f"Vision proxy request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Vision service error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in vision proxy: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/health")
async def proxy_health():
    """Health check for proxy service."""
    return {
        "status": "ok",
        "llm_configured": bool(getattr(settings, 'OPENAI_API_KEY', None)),
        "embedding_configured": bool(settings.EMBEDDING_MODEL_NAME),
    }
