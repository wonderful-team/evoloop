import os
import logging
from typing import Any, Dict, List
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

class LearningPromptBuilder:
    """
    Constructs prompts for the Learning module using Jinja2 templates.
    """
    def __init__(self):
        # Look for templates in the sibling directory
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def build_synthesis_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the skill synthesis prompt."""
        try:
            template = self.env.get_template("skill_synthesis.prompt.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Synthesis template: {e}")
            return f"Error loading skill synthesis template: {e}"

    def build_macro_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the smart replay macro generation prompt."""
        try:
            template = self.env.get_template("smart_replay_macro.prompt.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Macro template: {e}")
            return f"Error loading macro generation template: {e}"

    def build_phases_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the phase understanding prompt."""
        try:
            template = self.env.get_template("smart_replay_phases.prompt.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Phases template: {e}")
            return f"Error loading phases template: {e}"

    def build_metadata_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the skill metadata generation prompt."""
        try:
            template = self.env.get_template("smart_replay_metadata.prompt.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Metadata template: {e}")
            return f"Error loading metadata template: {e}"
