"""
Response rendering utilities using Jinja2 templates.

This module provides standardized response rendering functions used across
the application for consistent output formatting.
"""
import os
from typing import Any
from jinja2 import Environment, FileSystemLoader

# Setup Jinja2 Environment for response templates
_TEMPLATE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "config", "templates"
)
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))


def render_template(template_name: str, **kwargs: Any) -> str:
    """
    Render a template with the given context.

    Args:
        template_name: Name of the template file (e.g., "report/response.prompt.j2")
        **kwargs: Template context variables

    Returns:
        Rendered template string

    Raises:
        jinja2.TemplateNotFound: If the template does not exist
    """
    return _jinja_env.get_template(template_name).render(**kwargs)
