"""
Response rendering utilities using Jinja2 templates.

⚠️ DEPRECATED: This module is deprecated. Use `app.utils.template` instead.

This module now re-exports functions from `app.utils.template` for backward compatibility.
"""
import warnings
from typing import Any

# Re-export from template.py to avoid duplicate Environment instances
from app.utils.template import render_template

__all__ = ["render_template"]


def _deprecated_warning():
    """Warn about deprecated module usage."""
    warnings.warn(
        "app.utils.renderer is deprecated. Use app.utils.template instead.",
        DeprecationWarning,
        stacklevel=2,
    )
