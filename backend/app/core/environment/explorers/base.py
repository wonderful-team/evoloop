
import json
import logging
from abc import ABC, abstractmethod

from app.infrastructure.llm.factory import get_default_llm
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
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = await get_default_llm(temperature=0)

            prompt = render_template(
                "planning/explorer_triage.prompt.j2",
                system_role=f"You are an expert at identifying high-value productivity/lifestyle {platform} apps from their names.",
                platform=platform,
                items=items
            )

            role_name = render_template("planning/expert_roles.prompt.j2", role="knowledge_triage", platform=platform).strip()

            response = await llm.ainvoke([
                SystemMessage(content=role_name),
                HumanMessage(content=prompt)
            ])

            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()

            data = json.loads(content)
            return data.get("selected", {})
        except Exception as e:
            logger.warning(f"Intelligent Triage failed for {platform}: {e}")
            return {}
