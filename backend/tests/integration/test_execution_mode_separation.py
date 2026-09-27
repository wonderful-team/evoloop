"""Integration: execution-mode facts are driven by settings, not DB SystemConfig.

图引擎的 node_utils（get_displayed_execution_mode / get_mapped_cwd）已随重构删除；
此处仅保留仍有效的 `get_execution_mode` / `is_docker_mode` 事实层验证。
"""

from __future__ import annotations

from app.core.config import settings
from app.core.execution.execution_mode import get_execution_mode, is_docker_mode


class TestExecutionModeFacts:
    def test_local_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "local")
        assert get_execution_mode() == "local"
        assert is_docker_mode() is False

    def test_docker_mode(self, monkeypatch):
        monkeypatch.setattr(settings, "EXECUTION_MODE", "docker")
        assert get_execution_mode() == "docker"
        assert is_docker_mode() is True
