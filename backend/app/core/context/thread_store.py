import logging
import os
from threading import Lock

logger = logging.getLogger(__name__)


class ThreadContextStore:
    """
    Manages the working directory context and active project IDs for different threads (sessions).
    This allows the server to support multiple active projects simultaneously.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        # Mapping: thread_id -> working_directory path
        self._thread_contexts: dict[str, str] = {}
        # Mapping: thread_id -> project_id
        self._thread_projects: dict[str, int] = {}
        # Mapping: thread_id -> temporary project_id (for Scheme C)
        self._thread_temp_projects: dict[str, int] = {}
        # Legacy compatibility for plugins
        self._default_root = None

        logger.info("ThreadContextStore initialized.")

    @property
    def default_root(self) -> str:
        """
        Get the default root directory.
        Lazily attempts to load from DB, falling back to settings or home dir.

        多租户：默认根锁定为“当前 member 的工作根”（与 resolve_member_workspace_root
        同源）——全局 WORKSPACE_ROOT 是所有用户目录的父级，绝不能作为兜底 cwd。
        """
        # 优先从数据库获取（通过 get_workspace_root）。
        # 惰性导入：app.core.project.tools 会触发 evocloud_manager，顶层导入会造成
        # app.core.evocloud 初始化期的循环导入，导致服务无法启动。
        from app.core.config import settings as _settings
        from app.core.project.utils import (
            current_member_id,
            get_workspace_root,
            resolve_member_workspace_root,
        )

        db_root = get_workspace_root()
        if db_root:
            if _settings.MULTI_TENANT_MODE:
                member_root = resolve_member_workspace_root(current_member_id())
                if member_root:
                    return os.path.abspath(member_root)
                # member 未知：宁可拒绝也不能落到全局根（跨用户可见）
                return ""
            return os.path.abspath(db_root)

        # 最终回退：用户主目录
        return os.path.expanduser("~")

    def set_working_directory(self, thread_id: str, path: str):
        """Set the working directory for a specific thread.

        多租户守门：写入路径必须落在当前 member 的工作根内（按用户隔离的
        数据面边界——防止 request/事件/HITL 等入口把其他用户路径或宿主
        任意路径植入线程）。member 未知时拒绝落盘（fail-closed）。
        """
        if not path:
            logger.warning(f"Attempted to set empty path for thread {thread_id}")
            return

        from app.core.config import settings as _settings

        if _settings.MULTI_TENANT_MODE:
            from app.core.project.utils import (
                current_member_id,
                resolve_member_workspace_root,
            )

            member_root = resolve_member_workspace_root(current_member_id())
            if not member_root:
                logger.warning(
                    f"[ThreadStore] refuse to set working directory for {thread_id}: "
                    "member identity unknown in multi-tenant mode"
                )
                return
            normalized = os.path.realpath(path)
            member_root_real = os.path.realpath(member_root)
            # member root 自身是合法值——全局工作空间(0)的工作目录就是它
            if not (
                normalized == member_root_real
                or normalized.startswith(member_root_real + os.sep)
            ):
                logger.warning(
                    f"[ThreadStore] refuse working directory {path!r} for thread "
                    f"{thread_id}: outside member workspace {member_root!r}"
                )
                return

        # With API-driven projects, the path might be on a remote server (conceptually)
        # But for EvoLoop to work, it must be mounted/present locally at 'path'.
        # We assume 'external_path' from API maps to a valid local path.
        if not os.path.exists(path):
            logger.warning(
                f"Setting working directory to non-existent path: {path}. Agent actions might fail."
            )

        self._thread_contexts[thread_id] = path
        logger.info(f"Updated working directory for thread {thread_id} -> {path}")

    def set_active_project(self, thread_id: str, project_id: int):
        """Set the active project ID for a specific thread."""
        # Note: project_id can be 0 (global mode), so use 'is not None' check
        if project_id is not None:
            self._thread_projects[thread_id] = project_id

    def get_working_directory(self, thread_id: str) -> str:
        """Get the working directory for a specific thread. Returns default if not set."""
        path = self._thread_contexts.get(thread_id)
        if path:
            return path
        return self.default_root

    def get_active_project(self, thread_id: str) -> int | None:
        """Get the active project ID for a specific thread."""
        # First check for temporary project (Scheme C)
        temp_project = self._thread_temp_projects.get(thread_id)
        if temp_project is not None:
            return temp_project
        return self._thread_projects.get(thread_id)

    def set_temp_project(self, thread_id: str, project_id: int | None):
        """Set or clear the temporary project ID for a specific thread (Scheme C)."""
        if project_id is not None:
            self._thread_temp_projects[thread_id] = project_id
            logger.info(f"Set temporary project {project_id} for thread {thread_id}")
        else:
            self._thread_temp_projects.pop(thread_id, None)
            logger.info(f"Cleared temporary project for thread {thread_id}")

    def get_temp_project(self, thread_id: str) -> int | None:
        """Get the temporary project ID for a specific thread."""
        return self._thread_temp_projects.get(thread_id)


# Global instance
thread_context_store = ThreadContextStore()
