
import json
import logging
from abc import ABC, abstractmethod

from app.utils import render_template

logger = logging.getLogger(__name__)


class BaseExplorer(ABC):
    """
    Abstract Base Class for platform-specific environment explorers.
    """

    @abstractmethod
    async def scan(self, *args, **kwargs) -> list:
        """Perform a basic environment scan (e.g. list apps)."""
        pass

    @classmethod
    async def identify_high_value_apps(cls, items: list[str], platform: str) -> dict[str, dict]:
        """
        Shared LLM Triage logic.
        Returns mapping of {human_name: {"identifier": "...", "reasoning": "..."}}.
        """
        if not items:
            return {}

        try:
            prompt = render_template(
                "domain/planning/explorer_triage.prompt.j2",
                system_role=f"You are an expert at identifying high-value productivity/lifestyle {platform} apps from their names.",
                platform=platform,
                items=items
            )

            role_name = render_template("domain/planning/expert_roles.prompt.j2", role="knowledge_triage", platform=platform).strip()

            from app.core.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=[
                    {"role": "system", "content": role_name},
                    {"role": "user", "content": prompt}
                ],
                purpose="environment_triage",
                model_name=model_name,
            )

            content = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()

            data = json.loads(content)
            return data.get("selected", {})
        except Exception as e:
            logger.warning(f"Intelligent Triage failed for {platform}: {e}")
            return {}
