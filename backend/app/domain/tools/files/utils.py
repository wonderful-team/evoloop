import os

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.file import resolve_path
from app.core.tools import get_working_directory
from app.i18n.service import i18n
from app.infrastructure.config.service import SystemConfigService


async def resolve_and_validate_path(path: str, config: RunnableConfig | None = None) -> str:
    """
    Resolve path and perform security check.

    路径解析策略：
    - 路径以 uploads/ 开头（任意模式）
      → 物理根切换为 settings.CHAT_UPLOAD_DIR (~/.evoloop/uploads/)
      → 聊天附件统一存放在此，与项目模式完全无关
    - 其他路径
      → 使用 WORKSPACE_ROOT（或 working_directory）作为物理根
      → 如果目标文件不存在，自动回退到 CHAT_UPLOAD_DIR 中查找

    Raises ValueError on security violation or resolution failure.
    """
    if path.strip() in ("/", ""):
        path = "."

    root = get_working_directory(config)
    normalized_path = path.lstrip("/")

    # 获取当前会话 ID 以支持物理隔离
    thread_id = None
    if config:
        thread_id = config.get("configurable", {}).get("thread_id")

    if normalized_path.startswith("uploads/"):
        # 【统一映射】无论何种模式，uploads/ 始终指向聊天附件目录
        filename = normalized_path[len("uploads/"):]
        
        # 优先级 1: 会话隔离目录 (~/.evoloop/uploads/{thread_id}/)
        if thread_id:
            thread_isolated_path = os.path.join(settings.CHAT_UPLOAD_DIR, thread_id, filename)
            if os.path.exists(thread_isolated_path):
                return thread_isolated_path
        
        # 优先级 2: 全局目录 (~/.evoloop/uploads/global/)
        global_path = os.path.join(settings.CHAT_UPLOAD_DIR, "global", filename)
        if os.path.exists(global_path):
            return global_path
            
        # 优先级 3: 根目录 (向后兼容旧版 ~/.evoloop/uploads/)
        legacy_path = os.path.join(settings.CHAT_UPLOAD_DIR, filename)
        if os.path.exists(legacy_path):
            return legacy_path
            
        # 如果都不存在，默认返回会话隔离路径（用于后续写入或报错提示）
        root = os.path.join(settings.CHAT_UPLOAD_DIR, thread_id if thread_id else "global")
        target_path = resolve_path(filename, base_path=root)
    else:
        # 【常规路径】尝试从 WORKSPACE_ROOT 解析
        workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        if workspace_root:
            root = workspace_root
            
        target_path = resolve_path(path, base_path=root)

        # 【智能回退】尝试在所有可能的上传子目录中查找（跨会话搜索保护已在 resolve_path 外层处理）
        if target_path and not os.path.exists(target_path):
            # 同样遵循优先级
            if thread_id:
                fallback = os.path.join(settings.CHAT_UPLOAD_DIR, thread_id, normalized_path)
                if os.path.exists(fallback): return fallback
            
            fallback_global = os.path.join(settings.CHAT_UPLOAD_DIR, "global", normalized_path)
            if os.path.exists(fallback_global): return fallback_global
            
            fallback_legacy = os.path.join(settings.CHAT_UPLOAD_DIR, normalized_path)
            if os.path.exists(fallback_legacy): return fallback_legacy

    if not target_path:
        raise ValueError(i18n.get("domain_tools.files.resolve_error", path=path))

    # Security Check
    is_safe = target_path.startswith(root)
    if not is_safe:
        for prefix in settings.ALLOWED_PATH_PREFIXES:
            if target_path.startswith(prefix):
                is_safe = True
                break

    if not is_safe:
        raise ValueError(i18n.get("domain_tools.files.security_violation", path=path, root=root))

    return target_path
