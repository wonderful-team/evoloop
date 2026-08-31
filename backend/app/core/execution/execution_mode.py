"""Process execution-mode facts.

单一出处：当前进程实际以 ``local`` / ``docker`` 哪种模式运行，直接从
``settings.EXECUTION_MODE`` 读取，无任何覆写。沙箱构建（SandboxFactory）与 HITL
豁免（hitl_enabled）必须跟随进程真实模式。

（旧图引擎的 ``node_utils.get_displayed_execution_mode`` 表现层覆写已随重构删除。）
"""

from app.core.config import settings


def get_execution_mode() -> str:
    """Current process execution mode, normalized to lowercase (``local``/``docker``)."""
    return str(settings.EXECUTION_MODE).lower()


def is_docker_mode() -> bool:
    """Whether the current process runs with the docker sandbox."""
    return get_execution_mode() == "docker"
