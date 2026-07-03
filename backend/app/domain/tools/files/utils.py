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
      → 聊天附件统一存放在此，与工作空间模式完全无关
    - 其他路径
      → 使用 get_working_directory() 返回的根目录（已按 EvoContext.working_directory /
        config["configurable"]["working_directory"] / WORKSPACE_ROOT / os.getcwd() 优先级处理）

    Raises ValueError on security violation or resolution failure.
    """
    if path.strip() in ("/", ""):
        path = "."

    normalized_path = path.lstrip("/")

    # uploads/ 路径在所有模式下都允许，作为聊天附件的统一命名空间
    if normalized_path.startswith("uploads/"):
        return await _resolve_uploads_path(normalized_path, config)

    # 非 uploads 路径：允许访问。全局模式（project_id=0）下使用 WORKSPACE_ROOT 作为工作目录。
    # 具体项目的文件访问权限由 working_directory 和安全检查（target_path.startswith(root)）保证。
    # Security Check
    root = get_working_directory(config)
    target_path = resolve_path(path, base_path=root)

    if not target_path:
        raise ValueError(i18n.get("domain_tools.files.resolve_error", path=path))

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


async def _resolve_uploads_path(path: str, config: RunnableConfig | None = None) -> str:
    """
    Resolve uploads/ prefixed paths to the chat upload directory.

    无论何种模式，uploads/ 始终指向聊天附件目录，与会话隔离。
    """
    filename = path[len("uploads/") :]

    # 获取当前会话 ID 以支持物理隔离
    thread_id = None
    if config:
        thread_id = config.get("configurable", {}).get("thread_id")

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
    return resolve_path(filename, base_path=root)
