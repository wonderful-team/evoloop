"""
Template Rendering Utilities

Provides simplified interface for Jinja2 template rendering with common
configurations and helper functions.
"""

import os
from typing import Any

# Optional Jinja2 import
try:
    from jinja2 import BaseLoader, Environment, FileSystemLoader, Template
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False


def render_template(template_str: str, context: dict[str, Any]) -> str:
    """
    Render a Jinja2 template string with the given context.
    
    Args:
        template_str: Jinja2 template string
        context: Dictionary of variables for the template
    
    Returns:
        Rendered string
    
    Raises:
        ImportError: If Jinja2 is not installed
        Exception: If template rendering fails
    
    Example:
        >>> render_template("Hello {{ name }}!", {"name": "World"})
        'Hello World!'
    """
    if not HAS_JINJA2:
        # Simple fallback using str.replace for basic substitution
        result = template_str
        for key, value in context.items():
            result = result.replace(f"{{{{ {key} }}}}", str(value))
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result
    
    template = Template(template_str)
    return template.render(**context)


def render_template_file(template_path: str, context: dict[str, Any]) -> str:
    """
    Render a Jinja2 template file with the given context.
    
    Args:
        template_path: Path to the template file
        context: Dictionary of variables for the template
    
    Returns:
        Rendered string
    
    Raises:
        FileNotFoundError: If template file doesn't exist
        ImportError: If Jinja2 is not installed
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_str = f.read()
    
    return render_template(template_str, context)


def get_template_environment(template_dir: str, **kwargs: Any) -> "Environment | None":
    """
    Get a Jinja2 Environment for a template directory.
    
    Args:
        template_dir: Directory containing templates
        **kwargs: Additional arguments for Environment
    
    Returns:
        Jinja2 Environment or None if Jinja2 not installed
    """
    if not HAS_JINJA2:
        return None
    
    loader = FileSystemLoader(template_dir)
    return Environment(loader=loader, **kwargs)


def render_template_from_dir(
    template_name: str,
    template_dir: str,
    context: dict[str, Any]
) -> str:
    """
    Render a template from a directory.
    
    Args:
        template_name: Name of the template file
        template_dir: Directory containing templates
        context: Dictionary of variables for the template
    
    Returns:
        Rendered string
    """
    if not HAS_JINJA2:
        template_path = os.path.join(template_dir, template_name)
        return render_template_file(template_path, context)
    
    env = get_template_environment(template_dir)
    if env is None:
        raise ImportError("Jinja2 is required for template rendering")
    
    template = env.get_template(template_name)
    return template.render(**context)


class TemplateRenderer:
    """
    Reusable template renderer with configured environment.
    """
    
    def __init__(self, template_dir: str | None = None, **env_kwargs: Any):
        """
        Initialize template renderer.
        
        Args:
            template_dir: Optional directory for file templates
            **env_kwargs: Additional Jinja2 Environment options
        """
        self.template_dir = template_dir
        self.env: Environment | None = None
        
        if HAS_JINJA2 and template_dir:
            self.env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=env_kwargs.get('autoescape', True),
                **{k: v for k, v in env_kwargs.items() if k != 'autoescape'}
            )
    
    def render_string(self, template_str: str, **context: Any) -> str:
        """Render a template string."""
        return render_template(template_str, context)
    
    def render_file(self, template_name: str, **context: Any) -> str:
        """Render a template file."""
        if self.env is None:
            if self.template_dir:
                template_path = os.path.join(self.template_dir, template_name)
                return render_template_file(template_path, context)
            raise ValueError("No template directory configured")
        
        template = self.env.get_template(template_name)
        return template.render(**context)
    
    def add_global(self, name: str, value: Any) -> None:
        """Add a global variable to the template environment."""
        if self.env:
            self.env.globals[name] = value


# Common template filters
def register_common_filters(env: "Environment") -> None:
    """Register common filters with a Jinja2 environment."""
    if not HAS_JINJA2:
        return
    
    env.filters['basename'] = os.path.basename
    env.filters['dirname'] = os.path.dirname
    env.filters['splitext'] = lambda x: os.path.splitext(x)[0]
