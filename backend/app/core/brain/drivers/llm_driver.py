"""
Reflective Driver Implementation.
Adapts to external LLM APIs (Claude, OpenAI) for deep reasoning.
"""
import logging

from langchain_core.messages import SystemMessage, HumanMessage

from app.core.brain.drivers.abstract import BaseBrainDriver
from app.core.config import settings
from app.infrastructure.llm.factory import get_default_llm

logger = logging.getLogger(__name__)


class ReflectiveDriver(BaseBrainDriver):
    """
    Driver for the 'Reflective Brain' (Slow, External LLM).
    Used for memory consolidation and complex planning.
    """

    def __init__(self):
        self.mode = settings.REFLECTIVE_DRIVER_TYPE

    async def generate(self, context: str, user_input: str, system_prompt: str | None = None) -> str:
        """
        Calls external API via EvoLoop LLMFactory.
        """
        if self.mode == "mock":
            logger.info("Reflective Driver is in MOCK mode. Returning placeholder.")
            return "Reflective Thought (Mock): Consolidation requires a real LLM."

        try:
            # factory.create_llm() returns a LangChain Runnable
            model = get_default_llm(temperature=0.3)

            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))

            prompt_content = f"Context:\n{context}\n\nTask:\n{user_input}"
            messages.append(HumanMessage(content=prompt_content))

            logger.info("Reflective Driver invoking LLM...")
            response = await model.ainvoke(messages)

            return response.content
        except Exception as e:
            logger.error(f"Reflective Driver Failed: {e}")
            return f"Error executing reflective thought: {e}"

    async def health_check(self) -> bool:
        return True
