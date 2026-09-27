import asyncio
import logging

from app.core.config import settings
from app.core.execution.execution_mode import get_execution_mode
from app.core.execution.sandbox.base import Sandbox
from app.core.execution.sandbox.local import LocalSandbox

logger = logging.getLogger(__name__)


class SandboxFactory:
    """按 member 维度管理沙箱实例。

    - 多租户（MULTI_TENANT_MODE=true）：每个会员独立沙箱容器，仅挂载其
      ``workspace/<member_id>``。fail-closed：镜像缺失 / 初始化失败一律抛错，
      **绝不回退 LocalSandbox**（那是宿主机全权限进程，会击穿用户隔离）。
    - 单用户模式：沿用原行为（docker 失败回退 LocalSandbox，本地信任模型不变）。

    Docker init（``docker.from_env`` + 容器启动）是阻塞调用，在线程中执行
    以免阻塞事件循环。实例字典按 member_id 键控，锁保护首次初始化。
    """

    _instances: dict[int, Sandbox] = {}
    _init_lock = asyncio.Lock()

    @classmethod
    async def get_sandbox(cls, member_id: int = 0) -> Sandbox:
        """Return the sandbox for ``member_id``, initializing it off the event loop."""
        try:
            key = int(member_id) if member_id else 0
        except (TypeError, ValueError):
            key = 0

        existing = cls._instances.get(key)
        if existing:
            return existing

        async with cls._init_lock:
            existing = cls._instances.get(key)
            if existing:
                return existing

            # 事实层单一出处：SandboxFactory 与 hitl_enabled 共用同一判定，
            # 不读 SystemConfig 表覆写（后者仅供 prompt 渲染）。
            mode = get_execution_mode()
            image = settings.SANDBOX_IMAGE
            multi_tenant = settings.MULTI_TENANT_MODE

            if multi_tenant and key <= 0:
                raise RuntimeError(
                    "[SandboxFactory] member identity required in multi-tenant mode; "
                    "refusing to create a sandbox without per-user isolation"
                )

            logger.info(f"Initializing Sandbox in mode: {mode} for member {key}")

            if mode == "docker":
                try:
                    from app.core.execution.sandbox.docker import DockerSandbox

                    def _init_docker_sandbox() -> Sandbox:
                        # 预检查本地镜像：多租户主机常无 sandbox 镜像，
                        # 避免每次 docker pull 404 报错 + 2s 延迟。
                        import docker as docker_sdk

                        client = docker_sdk.from_env()
                        refs = client.images.list(filters={"reference": image})
                        if not refs:
                            refs = client.images.list(
                                filters={"reference": f"{image}:latest"}
                            )
                        if not refs:
                            # 多租户 fail-closed：无隔离容器绝不落回宿主进程执行
                            if multi_tenant:
                                raise RuntimeError(
                                    f"[SandboxFactory] Docker image '{image}' not "
                                    "found locally; per-user isolation requires it — "
                                    "build it with: docker build -f "
                                    "backend/Dockerfile.sandbox -t evoloop-sandbox backend/"
                                )
                            logger.info(
                                f"[SandboxFactory] Docker image '{image}' not found "
                                "locally; using LocalSandbox (pull skipped)"
                            )
                            return LocalSandbox()
                        return DockerSandbox(image, member_id=key)

                    cls._instances[key] = await asyncio.to_thread(_init_docker_sandbox)
                except Exception as e:
                    if multi_tenant:
                        # fail-closed：隔离是硬性要求，任何初始化失败都拒绝执行
                        raise
                    logger.exception(
                        f"Failed to initialize Docker Sandbox, falling back to Local: {e}"
                    )
                    cls._instances[key] = LocalSandbox()
            else:
                if multi_tenant:
                    raise RuntimeError(
                        f"[SandboxFactory] current execution mode '{mode}' has no "
                        "container isolation; per-user isolation is mandatory in "
                        "multi-tenant mode (set EXECUTION_MODE=docker)"
                    )
                cls._instances[key] = LocalSandbox()

        return cls._instances[key]

    @classmethod
    def reset(cls):
        """Tear down all cached sandbox instances (config change / shutdown)."""
        for _key, instance in list(cls._instances.items()):
            try:
                instance.teardown()
            except Exception as e:
                logger.warning(f"Sandbox teardown failed: {e}", exc_info=True)
        cls._instances.clear()

    @classmethod
    def reset_member(cls, member_id: int):
        """Tear down the sandbox of a single member (logout / logout events)."""
        try:
            key = int(member_id)
        except (TypeError, ValueError):
            return
        instance = cls._instances.pop(key, None)
        if instance:
            try:
                instance.teardown()
            except Exception as e:
                logger.warning(f"Sandbox teardown failed: {e}", exc_info=True)
