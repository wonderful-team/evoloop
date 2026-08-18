import logging

from app.core.config import settings
from app.core.execution.sandbox.base import Sandbox
from app.core.execution.sandbox.local import LocalSandbox

# Defer import of DockerSandbox to prevent failure if docker not installed?
# Or just import it.

logger = logging.getLogger(__name__)


class SandboxFactory:
    _instance: Sandbox | None = None

    @classmethod
    def get_sandbox(cls) -> Sandbox:
        if cls._instance:
            return cls._instance

        mode = settings.EXECUTION_MODE.lower()
        image = settings.SANDBOX_IMAGE

        logger.info(f"Initializing Sandbox in mode: {mode}")

        if mode == "docker":
            try:
                from app.core.execution.sandbox.docker import DockerSandbox

                cls._instance = DockerSandbox(image_name=image)
            except Exception as e:
                logger.exception(f"Failed to initialize Docker Sandbox, falling back to Local: {e}")
                cls._instance = LocalSandbox()
        else:
            cls._instance = LocalSandbox()

        return cls._instance

    @classmethod
    def reset(cls):
        if cls._instance:
            cls._instance.teardown()
            cls._instance = None
