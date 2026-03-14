"""
SSM Driver Implementation.
Uses LLMFactory for unified API access.
"""
import logging

from app.core.brain.drivers.abstract import BaseBrainDriver
from app.core.config import settings

logger = logging.getLogger(__name__)


class SSMDriver(BaseBrainDriver):
    def __init__(self):
        self.client = None
        self.mode = "mock" # Default to mock until initialized

    async def initialize(self):
        """
        Initialize the connection to the Flash Brain (SSM/Mamba) via LLMFactory.
        """
        try:
            from app.infrastructure.llm.factory import LLMFactory

            # Use Factory to create client
            self.client = LLMFactory.create_completion_client(
                base_url=settings.SSM_API_BASE,
                api_key="dummy", # Local servers usually ignore this
                model_name=settings.SSM_MODEL_NAME,
                temperature=0.7
            )

            if self.client:
                self.mode = "active"
                logger.info(f"Flash Brain (SSM) initialized at {settings.SSM_API_BASE} (Model: {settings.SSM_MODEL_NAME})")
            else:
                logger.warning("Flash Brain Client creation failed. Falling back to Mock.")
                self.mode = "mock"

        except Exception as e:
            logger.error(f"Flash Brain Initialization Failed: {e}. Falling back to Mock.")
            self.mode = "mock"

    async def generate(self, context: str, user_input: str, system_prompt: str | None = None) -> str:
        """
        Generates text using the standardized client.
        """
        if self.mode == "active" and self.client:
            full_prompt = f"{system_prompt or ''}\n{context}\nUser: {user_input}\nAssistant:"
            try:
                # LangChain OpenAI wrapper supports async ainvoke
                return await self.client.ainvoke(full_prompt)
            except Exception as e:
                logger.error(f"Flash Brain Inference Failed: {e}")
                return f"Brain Error: {e}"

        # Mock Mode / Fallback
        logger.debug(f"[SSM Mock Input]: {user_input[:50]}...")
        if "remember" in user_input.lower() and "project" in user_input.lower():
            return 'I will save that. <cmd>write_file path="working/current_task.md" content="User is working on a specific project."</cmd>'
        return "I am the Flash Brain (Mock Mode). Configure SSM_API_BASE to enable real inference."

    async def health_check(self) -> bool:
        if self.mode == "active" and self.client:
            try:
                # Simple ping
                await self.client.ainvoke("ping")
                return True
            except:
                return False
        return True
