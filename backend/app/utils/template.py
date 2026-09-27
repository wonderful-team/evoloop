"""
Template Rendering Utilities

Provides simplified interface for Jinja2 template rendering with common
configurations and helper functions.
"""

import os
from typing import Any

# Optional Jinja2 import
try:
    from jinja2 import Environment, FileSystemLoader

    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False


# Global environment for app/config/templates
_CONFIG_TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "templates"))
_config_env: "Environment | None" = None


def _truncate_list(items: list, max_items: int = 10) -> list:
    """Truncate a list to a maximum number of items."""
    return items[:max_items] if items else []


def _get_config_env() -> "Environment":
    """Get or create the global config templates environment."""
    global _config_env
    if _config_env is None and HAS_JINJA2:
        _config_env = Environment(loader=FileSystemLoader(_CONFIG_TEMPLATE_DIR))
        # Register custom filters
        _config_env.filters["truncate_list"] = _truncate_list
    if _config_env is None:
        raise ImportError("Jinja2 is required for template rendering")
    return _config_env


def render_template(template_name: str, **kwargs: Any) -> str:
    """
    Render a template from app/config/templates directory.

    This is the primary method for rendering prompt templates used across
    the application. Template paths are specified relative to
    app/config/templates (e.g., "common/report/response.prompt.j2").

    Args:
        template_name: Name/path of the template file (e.g., "common/report/response.prompt.j2")
        **kwargs: Template context variables

    Returns:
        Rendered template string

    Raises:
        jinja2.TemplateNotFound: If the template does not exist
        ImportError: If Jinja2 is not installed

    Example:
        >>> render_template("common/report/response.prompt.j2", success=True, message="Done")
        '✅ Done'
    """
    env = _get_config_env()
    template = env.get_template(template_name)
    return template.render(**kwargs)



