import asyncio
import logging

from app.core.config import settings
from app.core.execution.execution_mode import get_execution_mode
from app.core.execution.sandbox.base import Sandbox
from app.core.execution.sandbox.local import LocalSandbox

logger = logging.getLogger(__name__)


class SandboxFactory:
    _instance: Sandbox | None = None
    _init_lock = asyncio.Lock()

    @classmethod
    async def get_sandbox(cls) -> Sandbox:
        """Return the sandbox singleton, initializing it off the event loop.

        Docker init (``docker.from_env`` + container start) is a blocking
        network/daemon call, so it runs in a worker thread to avoid stalling
        the event loop. If docker mode fails, falls back to LocalSandbox.
        """
        if cls._instance:
            return cls._instance

        async with cls._init_lock:
            if cls._instance:
                return cls._instance

            # 事实层单一出处：SandboxFactory 与 hitl_enabled 共用同一判定，
            # 不读 SystemConfig 表覆写（后者仅供 prompt 渲染）。
            mode = get_execution_mode()
            image = settings.SANDBOX_IMAGE

            logger.info(f"Initializing Sandbox in mode: {mode}")

            if mode == "docker":
                try:
                    from app.core.execution.sandbox.docker import DockerSandbox

                    def _init_docker_sandbox():
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
                            logger.info(
                                f"[SandboxFactory] Docker image '{image}' not found "
                                "locally; using LocalSandbox (pull skipped)"
                            )
                            return LocalSandbox()
                        return DockerSandbox(image)

                    cls._instance = await asyncio.to_thread(_init_docker_sandbox)
                except Exception as e:
                    logger.exception(
                        f"Failed to initialize Docker Sandbox, falling back to Local: {e}"
                    )
                    cls._instance = LocalSandbox()
            else:
                cls._instance = LocalSandbox()

        return cls._instance

    @classmethod
    def reset(cls):
        if cls._instance:
            try:
                cls._instance.teardown()
            except Exception as e:
                logger.warning(f"Sandbox teardown failed: {e}", exc_info=True)
            cls._instance = None
