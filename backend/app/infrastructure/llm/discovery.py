"""Model Discovery Service — auto-detect local LLM providers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 3.0  # seconds per probe


@dataclass
class DiscoveredModel:
    id: str
    name: str
    source: str              # "lm-studio" | "ollama" | "custom"
    model_name: str
    base_url: str | None = None
    api_key: str | None = None
    capabilities: list[str] = field(default_factory=lambda: ["chat"])
    status: str = "unknown"  # "available" | "unavailable"
    context_window: int | None = None
    error: str | None = None


class ModelDiscoveryService:
    @staticmethod
    async def discover_all() -> list[DiscoveredModel]:
        """Run all discovery probes in parallel and return unified list."""
        tasks = [
            ModelDiscoveryService._probe_lm_studio(),
            ModelDiscoveryService._probe_ollama(),
            ModelDiscoveryService._probe_custom_config(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        models: list[DiscoveredModel] = []
        for r in results:
            if isinstance(r, Exception):
                logger.debug("[Discovery] Probe error (non-fatal): %s", r)
                continue
            models.extend(r)

        # Deduplicate by id
        seen: set[str] = set()
        unique: list[DiscoveredModel] = []
        for m in models:
            if m.id not in seen:
                seen.add(m.id)
                unique.append(m)
        return unique

    # ---- probes -----------------------------------------------------------

    @staticmethod
    async def _probe_lm_studio() -> list[DiscoveredModel]:
        """Probe LM Studio at localhost:1234."""
        base = "http://localhost:1234/v1"
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.get(f"{base}/models")
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.debug("[Discovery] LM Studio not available: %s", e)
            return []

        models: list[DiscoveredModel] = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if not model_id:
                continue
            models.append(
                DiscoveredModel(
                    id=f"lm-studio:{model_id}",
                    name=f"{model_id} (LM Studio)",
                    source="lm-studio",
                    model_name=model_id,
                    base_url=base,
                    api_key="lm-studio",
                    capabilities=["chat", "embedding"],
                    status="available",
                    context_window=8192,
                )
            )
        return models

    @staticmethod
    async def _probe_ollama() -> list[DiscoveredModel]:
        """Probe Ollama at localhost:11434."""
        base = "http://localhost:11434"
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.get(f"{base}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.debug("[Discovery] Ollama not available: %s", e)
            return []

        models: list[DiscoveredModel] = []
        for item in data.get("models", []):
            name = item.get("name", "")
            if not name:
                continue
            models.append(
                DiscoveredModel(
                    id=f"ollama:{name}",
                    name=f"{name} (Ollama)",
                    source="ollama",
                    model_name=name,
                    base_url=f"{base}/v1",
                    api_key="",
                    capabilities=["chat", "embedding"],
                    status="available",
                    context_window=8192,
                )
            )
        return models

    @staticmethod
    async def _probe_custom_config() -> list[DiscoveredModel]:
        """Check if user has a custom LLM configured."""
        from app.infrastructure.config import SystemConfigService

        try:
            base_url = SystemConfigService.get_value("LLM_BASE_URL")
            model = SystemConfigService.get_value("CUSTOM_LLM_MODEL")
            api_key = SystemConfigService.get_value("LLM_API_KEY")
        except Exception:
            return []

        if not base_url or not model:
            return []

        discovered: list[DiscoveredModel] = [
            DiscoveredModel(
                id=f"custom:{model}",
                name=f"{model} (Custom)",
                source="custom",
                model_name=model,
                base_url=base_url,
                api_key=api_key or "",
                capabilities=["chat"],
                status="available",
                context_window=128000,
            )
        ]
        return discovered
