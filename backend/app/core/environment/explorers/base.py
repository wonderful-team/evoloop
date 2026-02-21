
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from app.infrastructure.llm.vision import get_vision_llm

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
    async def identify_high_value_apps(cls, items: List[str], platform: str) -> Dict[str, dict]:
        """
        Shared LLM Triage logic.
        Returns mapping of {human_name: {"identifier": "...", "reasoning": "..."}}.
        """
        if not items:
            return {}

        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            llm = get_vision_llm(temperature=0)
            
            prompt = (
                f"You are an expert at identifying high-value productivity/lifestyle {platform} apps from their names.\n"
                f"Given this list of newly discovered {platform} apps/packages, identify which ones are important enough to warrant a 'Skill Probe'.\n"
                "Prioritize: Banking, Shopping, Travel, Social, Work Tools, Development Tools.\n"
                "Exclude: System services, drivers, small utilities, or low-utility settings.\n\n"
                "Respond ONLY with a JSON object:\n"
                "{\"selected\": {\"AppName\": {\"id\": \"identifier\", \"reason\": \"...\"}}}\n\n"
                "Items:\n" + "\n".join(items)
            )

            response = await llm.ainvoke([
                SystemMessage(content=f"You are a {platform.capitalize()} Knowledge Triage Agent."),
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
