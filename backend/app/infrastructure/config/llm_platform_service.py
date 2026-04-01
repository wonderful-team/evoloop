"""
LLM Platform Service - 从 EvoLoop Gateway 获取模型配置
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


@dataclass
class PlatformModel:
    """平台模型配置"""
    model_id: str
    display_name: str
    provider_name: str
    model_type: str  # llm, embedding, vision
    config_type: str  # evoloop, custom
    context_window: int
    max_tokens: int
    supports_streaming: bool
    supports_vision: bool
    supports_functions: bool
    description: str
    icon: str
    available: bool = True
    quota_required: bool = True


class LLMPlatformService:
    """
    从 Member Center API 获取 LLM 模型配置
    
    支持两种模式:
    - platform: 使用 EvoLoop 平台提供的模型 (需要配额)
    - custom: 使用用户自己的 API Key
    """
    
    _instance = None
    _models_cache: Dict[str, PlatformModel] = {}
    _last_fetch_time: float = 0
    _cache_ttl: int = 300  # 5分钟缓存
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def fetch_platform_models(self) -> List[PlatformModel]:
        """
        从 MC API 获取平台模型列表
        """
        import time
        import aiohttp
        
        # 检查缓存
        current_time = time.time()
        if self._models_cache and (current_time - self._last_fetch_time) < self._cache_ttl:
            return list(self._models_cache.values())
        
        # 获取 token
        token = evocloud_manager.get_token()
        if not token:
            logger.warning("[LLMPlatform] No token available, skipping platform models fetch")
            return []
        
        # 构建请求
        base_url = evocloud_manager.api.base_url if evocloud_manager.api else ""
        if not base_url:
            logger.warning("[LLMPlatform] No API base URL available")
            return []
        
        url = f"{base_url}/api/evoloop/llm/models"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error(f"[LLMPlatform] Failed to fetch models: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    
                    if data.get("code", -1) != 0:
                        logger.error(f"[LLMPlatform] API error: {data.get('message', 'unknown')}")
                        return []
                    
                    # 解析模型列表
                    models_data = data.get("data", {})
                    models = models_data.get("models", [])
                    
                    platform_models = []
                    for m in models:
                        if m.get("config_type") != "evoloop":
                            continue
                            
                        model = PlatformModel(
                            model_id=m.get("model_id", ""),
                            display_name=m.get("display_name", ""),
                            provider_name=m.get("provider_name", ""),
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
                    
                    self._last_fetch_time = current_time
                    
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
    获取可用的 LLM 模型列表
    
    根据配置类型返回合适的模型:
    - platform: 只返回平台提供的模型 (需要配额)
    - custom: 只返回自定义模型 (用户自己的 API Key)
    - None: 返回所有模型
    
    合并:
    1. 平台提供的模型 (从 MC API 获取)
    2. 自定义模型 (本地配置)
    """
    from app.constants import PRESET_LLM_MODELS
    from app.infrastructure.config.service import SystemConfigService
    
    # 如果未指定 config_type，从系统配置获取
    if config_type is None:
        config_type = SystemConfigService.get_value("LLM_CONFIG_TYPE", "custom")
    
    # 获取平台模型
    platform_models = await llm_platform_service.fetch_platform_models()
    
    # 转换平台模型格式
    platform_result = []
    for m in platform_models:
        platform_result.append({
            "id": m.model_id,
            "name": m.display_name,
            "type": "platform",
            "provider": m.provider_name,
            "model": m.model_id,
            "vision_model": m.model_id if m.supports_vision else None,
            "description": m.description or f"使用 EvoLoop 平台提供的 {m.display_name}",
            "icon": m.icon,
            "available": m.available,
            "quota_required": m.quota_required,
            "supports_streaming": m.supports_streaming,
            "supports_vision": m.supports_vision,
            "supports_functions": m.supports_functions,
            "context_window": m.context_window,
        })
    
    # 获取自定义模型 (保留原有的)
    custom_models = [m for m in PRESET_LLM_MODELS if m.get("type") == "custom"]
    
    # 根据 config_type 过滤
    if config_type == "platform":
        return platform_result
    elif config_type == "custom":
        return custom_models
    else:
        return platform_result + custom_models


async def get_available_embedding_models() -> List[Dict[str, Any]]:
    """
    获取所有可用的 Embedding 模型列表
    """
    from app.constants import PRESET_EMBEDDING_MODELS
    
    # 获取平台模型
    platform_models = await llm_platform_service.fetch_platform_models()
    
    # 过滤出 embedding 模型
    platform_result = []
    for m in platform_models:
        if m.model_type != "embedding":
            continue
            
        platform_result.append({
            "id": f"embedding-{m.model_id}",
            "name": m.display_name,
            "type": "platform",
            "provider": m.provider_name,
            "model": m.model_id,
            "dimensions": 1536,  # 默认值，实际应从配置获取
            "description": m.description or f"使用 EvoLoop 平台提供的 {m.display_name}",
            "icon": m.icon,
            "available": m.available,
            "quota_required": m.quota_required,
        })
    
    # 获取自定义模型
    custom_models = [m for m in PRESET_EMBEDDING_MODELS if m.get("type") == "custom"]
    
    return platform_result + custom_models
