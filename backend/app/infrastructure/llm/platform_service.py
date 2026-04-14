"""
LLM Platform Service - 从 EvoLoop Gateway 获取模型配置

注：HTTP 请求逻辑已下沉到 EvoCloudHTTPClient，本模块只保留缓存和格式转换层
"""
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional

from app.core.evocloud import evocloud_manager
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class PlatformModel(DynamicBaseModel):
    """平台模型配置"""
    model_id: str
    display_name: str
    provider_name: str
    provider_type: str = "openai"  # openai | anthropic
    model_type: str = "llm"  # llm, embedding, vision
    config_type: str = "evoloop"  # evoloop, custom
    context_window: int = 8192
    max_tokens: int = 4096
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_functions: bool = True
    description: str = ""
    icon: str = "default"
    available: bool = True
    quota_required: bool = True


class LLMPlatformService:
    """
    从 EvoLoop Gateway 获取 LLM 模型配置 (带本地缓存)
    """
    
    _instance = None
    _models_cache: Dict[str, PlatformModel] = {}
    _last_fetch_time: float = 0
    _cache_ttl: int = 300  # 5分钟缓存
    _fetch_lock = None  # 并发控制锁，防止同时发起多个请求
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._fetch_lock = asyncio.Lock()
        return cls._instance
    
    async def fetch_platform_models(self) -> List[PlatformModel]:
        """
        从 EvoLoop Gateway 获取平台模型列表
        使用 EvoCloudHTTPClient 处理 HTTP 请求、认证和路由
        
        使用锁防止并发请求导致重复 fetch（竞争条件）
        """
        current_time = time.time()
        
        # 快速检查：缓存有效直接返回（无需加锁）
        if self._models_cache and (current_time - self._last_fetch_time) < self._cache_ttl:
            return list(self._models_cache.values())
        
        # 加锁：防止多个并发请求同时 fetch
        async with self._fetch_lock:
            # 双重检查：拿到锁后再次确认缓存是否已被其他协程更新
            if self._models_cache and (time.time() - self._last_fetch_time) < self._cache_ttl:
                return list(self._models_cache.values())
            
            try:
                # 使用标准化的 HTTP client（自动处理 SSL、认证、路由）
                resp = await evocloud_manager.api.get_llm_models()
                
                if resp.get("code", -1) != 0:
                    logger.error(f"[LLMPlatform] API error: {resp.get('message', 'unknown')}")
                    return []
                
                # 解析模型列表
                models_data = resp.get("data", {})
                models = models_data.get("models", [])
                
                platform_models = []
                for m in models:
                    if m.get("config_type") != "evoloop":
                        continue
                        
                    model = PlatformModel(
                        model_id=m.get("model_id", ""),
                        display_name=m.get("display_name", ""),
                        provider_name=m.get("provider_name", ""),
                        provider_type=m.get("provider_type", "openai"),
                        model_type=m.get("model_type", "llm"),
                        config_type=m.get("config_type", "evoloop"),
                        context_window=m.get("context_window", 8192),
                        max_tokens=m.get("max_tokens", 4096),
                        supports_streaming=m.get("supports_streaming", True),
                        supports_vision=m.get("supports_vision", False),
                        supports_functions=m.get("supports_functions", True),
                        description=m.get("description", ""),
                        icon=m.get("icon", "default"),
                        available=m.get("available", True),
                        quota_required=m.get("quota_required", True)
                    )
                    platform_models.append(model)
                    self._models_cache[model.model_id] = model
                
                self._last_fetch_time = time.time()
                
                logger.info(f"[LLMPlatform] Fetched {len(platform_models)} platform models")
                return platform_models
                    
            except Exception as e:
                logger.error(f"[LLMPlatform] Error fetching models: {e}")
                return []
    
    def get_cached_models(self) -> List[PlatformModel]:
        """获取缓存的模型列表"""
        return list(self._models_cache.values())
    
    def get_model_by_id(self, model_id: str) -> Optional[PlatformModel]:
        """根据 ID 获取模型配置"""
        return self._models_cache.get(model_id)
    
    def clear_cache(self):
        """清除缓存"""
        self._models_cache.clear()
        self._last_fetch_time = 0


# 全局实例
llm_platform_service = LLMPlatformService()


async def get_available_llm_models(config_type: str = None) -> List[Dict[str, Any]]:
    """
    获取可用的 LLM 模型列表 (platform + custom 组合)
    
    - platform: 从 EvoLoop Gateway 获取的模型（需要配额）
    - custom: 用户自己配置的模型（使用自己的 API Key）
    """
    from app.infrastructure.config.service import SystemConfigService
    
    # 如果未指定 config_type，从系统配置获取
    if config_type is None:
        config_type = SystemConfigService.get_value("LLM_CONFIG_TYPE", "platform")
    
    result = []
    
    # 1. 获取 Platform 模型（从 EvoLoop Gateway）
    platform_models = await llm_platform_service.fetch_platform_models()
    for m in platform_models:
        if m.model_type != "llm":  # 只保留 LLM 模型
            continue

        result.append({
            "id": m.model_id,
            "name": m.display_name,
            "type": "platform",
            "provider": m.provider_name,
            "provider_type": m.provider_type,
            "model": m.model_id,
            "vision_model": m.model_id if m.supports_vision else None,
            "description": m.description or f"使用 EvoLoop 平台提供的 {m.display_name}",
            "icon": m.icon,
            "available": m.available,
            "quota_required": True,
            "supports_streaming": m.supports_streaming,
            "supports_vision": m.supports_vision,
            "supports_functions": m.supports_functions,
            "context_window": m.context_window,
        })
    
    # 2. 获取 Custom 模型（用户自己配置的）
    custom_provider = SystemConfigService.get_value("LLM_PROVIDER")
    custom_provider_type = SystemConfigService.get_value("LLM_PROVIDER_TYPE", "openai")
    custom_model = SystemConfigService.get_value("LLM_MODEL")
    custom_base_url = SystemConfigService.get_value("LLM_BASE_URL")
    custom_api_key = SystemConfigService.get_value("LLM_API_KEY")
    
    if custom_provider and custom_model and custom_api_key:
        # 构建 custom 模型 ID
        custom_id = f"custom-{custom_provider}-{custom_model}"
        
        # 从配置获取 vision model
        vision_model = SystemConfigService.get_value("VISION_MODEL", custom_model)
        
        result.append({
            "id": custom_id,
            "name": f"{custom_model} (Custom)",
            "type": "custom",
            "provider": custom_provider,
            "provider_type": custom_provider_type,
            "model": custom_model,
            "vision_model": vision_model if vision_model != custom_model else None,
            "description": f"使用自己的 {custom_provider.upper()} API Key",
            "icon": custom_provider,
            "available": True,
            "quota_required": False,
            "supports_streaming": True,
            "supports_vision": custom_provider_type in ["openai", "anthropic"],
            "supports_functions": custom_provider_type in ["openai", "anthropic"],
            "context_window": 128000 if "gpt-4" in custom_model else 8192,
        })
    
    return result


async def get_available_embedding_models() -> List[Dict[str, Any]]:
    """
    获取可用的 Embedding 模型列表 (platform + custom 组合)
    
    - platform: 从 EvoLoop Gateway 获取的模型（需要配额）
    - custom: 用户自己配置的模型（使用自己的 API Key）
    """
    from app.infrastructure.config.service import SystemConfigService
    
    result = []
    
    # 1. 获取 Platform Embedding 模型（从 EvoLoop Gateway）
    platform_models = await llm_platform_service.fetch_platform_models()
    for m in platform_models:
        if m.model_type != "embedding":
            continue
            
        result.append({
            "id": f"embedding-{m.model_id}",
            "name": m.display_name,
            "type": "platform",
            "provider": m.provider_name,
            "model": m.model_id,
            "dimensions": 1536,  # 默认值，实际应从配置获取
            "description": m.description or f"使用 EvoLoop 平台提供的 {m.display_name}",
            "icon": m.icon,
            "available": m.available,
            "quota_required": True,
        })
    
    # 2. 获取 Custom Embedding 模型（用户自己配置的）
    embedding_provider = SystemConfigService.get_value("EMBEDDING_PROVIDER")
    embedding_model = SystemConfigService.get_value("EMBEDDING_MODEL")
    embedding_api_key = SystemConfigService.get_value("EMBEDDING_API_KEY")
    
    if embedding_provider and embedding_model and embedding_api_key:
        # 根据 provider 推断 dimensions
        dimensions_map = {
            "openai": 1536,
            "ollama": 768,
            "dashscope": 1536,
            "huggingface": 768,
        }
        dimensions = dimensions_map.get(embedding_provider, 1536)
        
        custom_id = f"custom-embedding-{embedding_provider}-{embedding_model}"
        
        result.append({
            "id": custom_id,
            "name": f"{embedding_model} (Custom)",
            "type": "custom",
            "provider": embedding_provider,
            "model": embedding_model,
            "dimensions": dimensions,
            "description": f"使用自己的 {embedding_provider.upper()} Embedding API Key",
            "icon": embedding_provider,
            "available": True,
            "quota_required": False,  # custom 模型不需要配额
        })
    
    return result
