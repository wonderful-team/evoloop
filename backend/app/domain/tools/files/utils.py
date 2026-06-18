import os

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.file import resolve_path
from app.core.tools import get_working_directory
from app.i18n.service import i18n


async def resolve_and_validate_path(
    path: str, config: RunnableConfig | None = None
) -> str:
    """
    Resolve path and perform security check.

    路径解析策略：
    - 路径以 uploads/ 开头（任意模式）
      → 物理根切换为 settings.CHAT_UPLOAD_DIR (~/.evoloop/uploads/)
      → 聊天附件统一存放在此，与项目模式完全无关
    - 其他路径
      → 使用 get_working_directory() 返回的根目录（已按 EvoContext.working_directory /
        config["configurable"]["working_directory"] / WORKSPACE_ROOT / os.getcwd() 优先级处理）

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
        filename = normalized_path[len("uploads/") :]

        # 优先级 1: 会话隔离目录 (~/.evoloop/uploads/{thread_id}/)
        if thread_id:
            thread_isolated_path = os.path.join(
                settings.CHAT_UPLOAD_DIR, thread_id, filename
            )
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
        root = os.path.join(
            settings.CHAT_UPLOAD_DIR, thread_id if thread_id else "global"
        )
        target_path = resolve_path(filename, base_path=root)
    else:
        # 【常规路径】使用 get_working_directory 提供的根目录
        # 该函数已按优先级处理 EvoContext.working_directory / config / WORKSPACE_ROOT
        target_path = resolve_path(path, base_path=root)

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
        raise ValueError(
            i18n.get("domain_tools.files.security_violation", path=path, root=root)
        )

    # Protect project metadata directory from agent file tools.
    if ".evoloop" in target_path.lower():
        raise ValueError(
            i18n.get(
                "domain_tools.files.security_violation",
                path=path,
                root="project metadata directory",
            )
        )

    return target_path
