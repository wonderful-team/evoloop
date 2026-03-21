import os
import logging
from typing import Any, Dict, List
from jinja2 import Environment, FileSystemLoader
from app.core.environment.capabilities.registry import ActionRegistry

logger = logging.getLogger(__name__)


class LearningPromptBuilder:
    """
    Constructs prompts for the Learning module using Jinja2 templates.
    """
    def __init__(self):
        # Look for templates in the sibling directory
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.env = Environment(loader=FileSystemLoader(template_dir))
        
    def _get_action_docs(self) -> Dict[str, List[str]]:
        """Organizes registry actions by platform for prompt optimization."""
        docs = {"dom": [], "mobile": [], "desktop": []}
        for action in ActionRegistry.list_actions():
            doc_str = f'- "{action.id}": {action.description}'
            if action.params:
                doc_str += f' Params: {", ".join(action.params.keys())}'
            
            for p in action.platforms:
                if p in docs:
                    docs[p].append(doc_str)
        return docs

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
            # Inject dynamic action documentation from the registry
            vars["action_docs"] = self._get_action_docs()
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

    def build_multimodal_synthesis_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the multimodal skill synthesis prompt."""
        try:
            template = self.env.get_template("multimodal_synthesis.prompt.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Multimodal Synthesis template: {e}")
            return f"Error loading multimodal synthesis template: {e}"

    def build_discovery_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the skill discovery (intent matching) prompt."""
        try:
            template = self.env.get_template("skill_discovery.prompt.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Discovery template: {e}")
            return f"Error loading skill discovery template: {e}"

    def build_multimodal_context_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the task context for multimodal synthesis."""
        try:
            template = self.env.get_template("multimodal_task_context.j2")
            return template.render(**vars)
        except Exception as e:
            logger.error(f"Error rendering Multimodal Context template: {e}")
            return f"Error loading multimodal context template: {e}"

    def build_synthesis_human_prompt(self, vars: Dict[str, Any] = None) -> str:
        """Renders the human prompt for skill synthesis."""
        try:
            template = self.env.get_template("synthesis_human.prompt.j2")
            return template.render(**(vars or {}))
        except Exception as e:
            logger.error(f"Error rendering Synthesis Human template: {e}")
            return "Please analyze the trace and generate the skill YAML."
