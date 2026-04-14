"""
Learning Module Event Handlers

订阅系统事件并处理学习模块相关的生命周期操作。
"""

import asyncio
import logging

from app.core.events import SystemEventType, system_bus

logger = logging.getLogger(__name__)


async def _warm_skills_cache():
    """Background task to warm skills discovery cache."""
    try:
        # Wait a bit for the main startup to complete
        await asyncio.sleep(0.5)
        from app.core.learning.discovery import skill_discovery
        skills = await skill_discovery.get_active_skills_list()
        logger.info(f"[Learning] ✓ Skills cache warmed: {len(skills)} skills")
    except Exception as e:
        logger.warning(f"[Learning] Skills cache warming failed: {e}")


async def _warm_user_preferences():
    """Background task to warm user preferences cache."""
    try:
        from app.infrastructure.config.service import SystemConfigService
        lang_pref = SystemConfigService.get_language_preference()
        logger.info(f"[Learning] ✓ User preferences cached: language={lang_pref}")
    except Exception as e:
        logger.warning(f"[Learning] User preferences caching failed: {e}")


async def on_application_started(event):
    """
    应用启动完成后，预热学习模块相关缓存。
    
    包括：
    1. Skills 发现缓存
    2. 用户偏好设置缓存
    """
    logger.info("[Learning] Application started event received, warming caches...")

    try:
        # 后台异步预热缓存（不阻塞启动）
        asyncio.create_task(_warm_skills_cache())
        asyncio.create_task(_warm_user_preferences())
    except Exception as e:
        logger.error(f"[Learning] Failed to start cache warming: {e}")


def register_learning_event_handlers():
    """
    注册学习模块事件处理器。
    
    在服务启动时调用。
    """
    # 订阅应用启动事件
    system_bus.subscribe(SystemEventType.APP_STARTED, on_application_started)

    logger.info("[Learning] Event handlers registered")
