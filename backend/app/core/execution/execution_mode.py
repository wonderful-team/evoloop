"""Process execution-mode facts.

单一出处：当前进程实际以 ``local`` / ``docker`` 哪种模式运行，直接从
``settings.EXECUTION_MODE`` 读取，无任何覆写。沙箱构建（SandboxFactory）与 HITL
豁免（hitl_enabled）必须跟随进程真实模式。

提示词/template 渲染用的可覆写模式见 ``node_utils.get_displayed_execution_mode``：
它允许 SystemConfig 表覆写，但那是表现层，**不**参与沙箱/HITL 判定。
"""

from app.core.config import settings


def get_execution_mode() -> str:
    """Current process execution mode, normalized to lowercase (``local``/``docker``)."""
    return str(settings.EXECUTION_MODE).lower()


def is_docker_mode() -> bool:
    """Whether the current process runs with the docker sandbox."""
    return get_execution_mode() == "docker"
