import logging
import asyncio
from typing import Optional

from langchain_openai import ChatOpenAI
# from langchain_anthropic import ChatAnthropic # Optional: if using Claude

try:
    from browser_use import Agent
    from browser_use.browser.browser import Browser, BrowserConfig
    from browser_use.browser.context import BrowserContextConfig
    HAS_BROWSER_USE = True
except ImportError:
    HAS_BROWSER_USE = False

from app.core.config import settings

logger = logging.getLogger(__name__)

class BrowserService:
    _instance = None
    
    def __init__(self):
        self.browser = None
        if HAS_BROWSER_USE:
             # Configure browser (headless=False for debug, True for prod)
             # We might want to make this configurable
             self.browser = Browser(
                 config=BrowserConfig(
                     headless=True, # Default to headless for server
                     disable_security=True
                 )
             )

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def run_task(self, task: str, session_id: str = None) -> str:
        """
        Run a browser task using browser-use Agent.
        """
        if not HAS_BROWSER_USE:
            return "Error: browser-use library not installed or Python version incompatible (requires >=3.11)."
            
        logger.info(f"Starting Browser Agent task: {task}")
        
        # Initialize LLM
        # ideally we use the project's standard LLM factory, but browser-use needs a powerful model (GPT-4o or Claude 3.5 Sonnet)
        # We'll default to GPT-4o if available in settings, or fallback.
        api_key = settings.OPENAI_API_KEY
        model_name = "gpt-4o"
        
        if not api_key:
            return "Error: OPENAI_API_KEY not configured."
            
        llm = ChatOpenAI(model=model_name, api_key=api_key)
        
        # Create Agent
        # We use a new context for each task for now, or persist if session_id provided?
        # For simplicity: One-off context
        async with await self.browser.new_context() as context:
            agent = Agent(
                task=task,
                llm=llm,
                browser_context=context,
                # generate_gif=False # Disable gif generation to save resources
            )
            
            try:
                history = await agent.run()
                
                # Extract Result
                # browser-use returns a history object. 
                # We try to get the final result.
                if history and hasattr(history, 'final_result'):
                     return history.final_result()
                
                # Fallback: check last item
                # This depends on browser-use version.
                # Assuming simple string return for now in case of recent API changes or just dump
                return str(history)

            except Exception as e:
                logger.error(f"Browser Agent failed: {e}")
                return f"Browser Agent failed: {e}"

    async def close(self):
        if self.browser:
            await self.browser.close()

# Global instance
browser_service = BrowserService.get_instance()
