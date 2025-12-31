import logging
import sys
import os
import asyncio
from typing import Optional
from app.utils.async_utils import run_in_thread

from app.core.config import settings

logger = logging.getLogger(__name__)

# Add Open-AutoGLM to sys.path
AUTOGLM_PATH = os.path.abspath(os.path.join(os.getcwd(), "../../Open-AutoGLM"))
if AUTOGLM_PATH not in sys.path:
    sys.path.append(AUTOGLM_PATH)

HAS_AUTOGLM = False
PhoneAgent = object
ModelConfig = object
AgentConfig = object

try:
    from phone_agent.agent import PhoneAgent, AgentConfig
    from phone_agent.model import ModelConfig
    HAS_AUTOGLM = True
except ImportError as e:
    logger.warning(f"Open-AutoGLM not found or missing dependencies: {e}")
    HAS_AUTOGLM = False

class MobileService:
    _instance = None
    
    def __init__(self):
        self.agent = None
        self._setup_agent()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _setup_agent(self):
        if not HAS_AUTOGLM:
            return

        try:
            # Model Config
            model_config = ModelConfig(
                base_url=settings.PHONE_AGENT_BASE_URL,
                model_name=settings.PHONE_AGENT_MODEL,
                api_key=settings.OPENAI_API_KEY, # Use OpenAI key if reused, or empty
                temperature=0.1
            )
            
            # Agent Config
            agent_config = AgentConfig(
                max_steps=50,
                device_id=settings.PHONE_AGENT_DEVICE_ID,
                lang=settings.PHONE_AGENT_LANG,
                verbose=True
            )
            
            self.agent = PhoneAgent(
                model_config=model_config,
                agent_config=agent_config
            )
            logger.info("Mobile Agent (AutoGLM) initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize Mobile Agent: {e}")
            self.agent = None

    async def run_task(self, instruction: str) -> str:
        if not HAS_AUTOGLM:
            return "Error: Open-AutoGLM library not found or dependencies missing."
        
        if not self.agent:
            return "Error: Mobile Agent failed to initialize (check logs for config/dependency errors)."

        logger.info(f"Starting Mobile Task: {instruction}")
        
        try:
            # Run blocking agent in executor
            result = await run_in_thread(self.agent.run, instruction)
            return str(result)
        except Exception as e:
            logger.error(f"Mobile Agent failed: {e}")
            return f"Mobile Agent failed: {e}"

# Global instance
mobile_service = MobileService.get_instance()
