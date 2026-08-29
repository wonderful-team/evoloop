import logging
from abc import ABC, abstractmethod
from typing import Any

from app.core.engine.nodes.utils.node_utils import (
    get_displayed_execution_mode,
    get_mapped_cwd,
    read_project_profile,
    to_template_context,
)

logger = logging.getLogger(__name__)


class BasePromptBuilder(ABC):
    """
    Abstract base class for all prompt builders in Evoloop.
    Enforces a common interface for building system prompts and provides shared utilities.
    """

    @abstractmethod
    def build(self, *args, **kwargs) -> str:
        """
        Builds the static, cacheable system prompt.

        All builders must implement this method to return their static prompt string.
        """
        pass

    def get_user_lang(self) -> str:
        """Helper to get user's language preference."""
        from app.infrastructure.config.service import SystemConfigService

        return SystemConfigService.get_language_preference()

    def get_displayed_execution_mode(self) -> str:
        """Helper to get the execution mode shown in the prompt (可覆写表现层)."""
        return get_displayed_execution_mode()

    def get_mapped_cwd(self, raw_cwd: str) -> str:
        """Helper to standardize and map the working directory path."""
        return get_mapped_cwd(raw_cwd)

    def read_project_profile(self, working_directory: str | None, log_prefix: str = "") -> str:
        """Helper to read PROJECT.md context from the working directory."""
        return read_project_profile(working_directory, log_prefix)

    def to_template_context(self, obj: Any) -> Any:
        """Helper to convert Pydantic models to Jinja2-safe plain Python contexts."""
        return to_template_context(obj)
