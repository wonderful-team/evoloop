"""
EvoCloud Event Handlers

订阅系统事件并处理 EvoCloud 相关的生命周期操作。
"""

import asyncio
import logging

from app.core.events import SystemEventType, system_bus
from app.core.evocloud.manager import evocloud_manager

logger = logging.getLogger(__name__)


async def _warm_evocloud_cache():
    """Background task to warm EvoCloud projects cache."""
    try:
        # Wait a bit for the main startup to complete
        await asyncio.sleep(1)
        projects = await evocloud_manager.scan_projects()
        logger.info(f"[EvoCloud] ✓ Projects cache warmed: {len(projects)} projects")
    except Exception as e:
        logger.warning(f"[EvoCloud] Cache warming failed: {e}")


async def _sync_cloud_project():
    """
    同步云端当前项目到本地。
    
    在 EvoCloud 服务启动后调用，检查云端活跃项目并同步到本地工作区。
    """
    try:
        import os

        from app.core.context import thread_context_store
        from app.domain.codebase.indexing.manager import indexing_manager
        from app.domain.codebase.indexing.service import IndexingService
        from app.domain.project import cache as project_cache

        res = await evocloud_manager.api.get_current_project()
        if res.get("code") == 0:
            project_data = res.get("data", {})
            cloud_path = project_data.get("external_path")
            if cloud_path and os.path.exists(cloud_path):
                # 检查项目是否被本地忽略
                is_ignored = await project_cache.is_path_ignored(cloud_path)
                if not is_ignored:
                    # 也检查 DB 中的忽略状态
                    service = IndexingService()
                    existing_repo = await service.get_repo_by_path(cloud_path)
                    if existing_repo and existing_repo.sync_status == "IGNORED":
                        is_ignored = True
                        logger.info(f"[EvoCloud] Project {cloud_path} is marked as IGNORED in DB. Skipping cloud sync.")

                if is_ignored:
                    logger.info(f"[EvoCloud] Skipping cloud project sync for ignored path: {cloud_path}")
                else:
                    logger.info(f"[EvoCloud] Synced active project from Cloud: {cloud_path}")
                    # 更新默认线程的工作目录
                    thread_context_store.set_working_directory("default", cloud_path)

                    project_id = project_data.get("project_id")
                    service = IndexingService()
                    repo_name = os.path.basename(cloud_path)
                    repo = await service.get_or_create_repo(cloud_path, repo_name, project_id=project_id)
                    await indexing_manager.start_watching(cloud_path, repo.id)
            else:
                logger.info(f"[EvoCloud] Cloud active project path invalid or local missing: {cloud_path}")
        else:
            logger.warning(f"[EvoCloud] Failed to fetch current project: {res.get('message')}")
    except Exception as e:
        logger.warning(f"[EvoCloud] Error syncing cloud project: {e}")


async def on_application_started(event):
    """
    应用启动完成后，启动 EvoCloud 服务。
    
    包括：
    1. WebSocket Link 连接
    2. 对话历史同步到 MC
    3. 云端项目同步
    4. 缓存预热（后台异步）
    """
    logger.info("[EvoCloud] Application started event received, initializing...")

    try:
        # 检查是否有持久化的 token
        if evocloud_manager.api and evocloud_manager.api.get_token():
            logger.info("[EvoCloud] Found persisted token, starting services...")
            await evocloud_manager.start()
            logger.info("[EvoCloud] Services started successfully")

            # 同步云端项目
            await _sync_cloud_project()

            # 后台异步预热缓存（不阻塞启动）
            asyncio.create_task(_warm_evocloud_cache())
        else:
            logger.info("[EvoCloud] No token found, skipping auto-start (will start after login)")
    except Exception as e:
        logger.error(f"[EvoCloud] Failed to start services: {e}")


async def on_application_stopping(event):
    """
    应用即将停止，清理 EvoCloud 资源。
    """
    logger.info("[EvoCloud] Application stopping event received, cleaning up...")

    try:
        await evocloud_manager.stop()
        logger.info("[EvoCloud] Services stopped successfully")
    except Exception as e:
        logger.error(f"[EvoCloud] Error during shutdown: {e}")


def register_evocloud_event_handlers():
    """
    注册 EvoCloud 事件处理器。
    
    在服务启动时调用。
    """
    # 订阅应用启动事件
    system_bus.subscribe(SystemEventType.APP_STARTED, on_application_started)

    # 订阅应用停止事件
    system_bus.subscribe(SystemEventType.APP_STOPPING, on_application_stopping)

    logger.info("[EvoCloud] Event handlers registered")
