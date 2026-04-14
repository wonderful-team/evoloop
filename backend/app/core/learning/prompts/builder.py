import logging
from typing import Any, Dict, List

from pydantic import Field

from app.core.environment.capabilities.registry import ActionRegistry
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils import render_template

logger = logging.getLogger(__name__)


class ActionRegistryItem(DynamicBaseModel):
    """Action metadata injected into prompt templates."""
    id: str
    description: str
    params: List[str] = Field(default_factory=list)
    platforms: List[str] = Field(default_factory=list)


class LearningPromptBuilder:
    """
    Constructs prompts for the Learning module using Jinja2 templates.
    
    This builder provides a centralized way to render learning-related prompts
    with consistent error handling and fallback mechanisms.
    """
    
    # Template name mapping for cleaner code
    TEMPLATES = {
        "synthesis": "learning/skill_synthesis.prompt.j2",
        "macro": "learning/smart_replay_macro.prompt.j2",
        "phases": "learning/smart_replay_phases.prompt.j2",
        "metadata": "learning/smart_replay_metadata.prompt.j2",
        "multimodal_synthesis": "learning/multimodal_synthesis.prompt.j2",
        "discovery": "learning/skill_discovery.prompt.j2",
        "multimodal_context": "learning/multimodal_task_context.j2",
        "synthesis_human": "learning/synthesis_human.prompt.j2",
        "task_complexity": "learning/task_complexity_analysis.prompt.j2",
    }
        
    def _get_actions(self) -> List[ActionRegistryItem]:
        """
        Get raw action registry data for template rendering.
        Returns structured data for Jinja2 template to format.
        """
        return [
            ActionRegistryItem(
                id=action.id,
                description=action.description,
                params=list(action.params.keys()) if action.params else [],
                platforms=action.platforms,
            )
            for action in ActionRegistry.list_actions()
        ]

    def _render_with_fallback(
        self, 
        template_key: str, 
        vars: Dict[str, Any], 
        fallback_msg: str = "Error loading template"
    ) -> str:
        """
        Generic template rendering with error handling.
        
        Args:
            template_key: Key in TEMPLATES dict
            vars: Template variables
            fallback_msg: Message prefix for fallback response
            
        Returns:
            Rendered template string or fallback message
        """
        template_name = self.TEMPLATES.get(template_key, template_key)
        try:
            return render_template(template_name, **vars)
        except Exception as e:
            logger.error(f"Error rendering {template_name}: {e}")
            return f"{fallback_msg}: {e}"

    def build_synthesis_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the skill synthesis prompt."""
        return self._render_with_fallback(
            "synthesis", 
            vars, 
            "Error loading skill synthesis template"
        )

    def build_macro_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the smart replay macro generation prompt."""
        # Inject raw action data for template to format
        vars["actions"] = self._get_actions()
        return self._render_with_fallback(
            "macro", 
            vars, 
            "Error loading macro generation template"
        )

    def build_phases_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the phase understanding prompt."""
        return self._render_with_fallback(
            "phases", 
            vars, 
            "Error loading phases template"
        )

    def build_metadata_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the skill metadata generation prompt."""
        return self._render_with_fallback(
            "metadata", 
            vars, 
            "Error loading metadata template"
        )

    def build_multimodal_synthesis_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the multimodal skill synthesis prompt."""
        return self._render_with_fallback(
            "multimodal_synthesis", 
            vars, 
            "Error loading multimodal synthesis template"
        )

    def build_discovery_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the skill discovery (intent matching) prompt."""
        return self._render_with_fallback(
            "discovery", 
            vars, 
            "Error loading skill discovery template"
        )

    def build_multimodal_context_prompt(self, vars: Dict[str, Any]) -> str:
        """Renders the task context for multimodal synthesis."""
        return self._render_with_fallback(
            "multimodal_context", 
            vars, 
            "Error loading multimodal context template"
        )

    def build_synthesis_human_prompt(self, vars: Dict[str, Any] = None) -> str:
        """Renders the human prompt for skill synthesis."""
        result = self._render_with_fallback(
            "synthesis_human", 
            vars or {}, 
            "Error loading synthesis human template"
        )
        # Special fallback for human prompt - provide a meaningful default
        if result.startswith("Error loading"):
            return "Please analyze the trace and generate the skill YAML."
        return result

    def build_task_complexity_prompt(self, query: str) -> str:
        """
        Renders the task complexity analysis prompt.
        
        Args:
            query: The task description to analyze
            
        Returns:
            Rendered prompt string for task complexity analysis
        """
        return self._render_with_fallback(
            "task_complexity",
            {"query": query},
            "Error loading task complexity analysis template"
        )
