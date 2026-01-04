import logging
import asyncio
import os
import glob
import shutil
from typing import Optional, Dict

from app.utils.id import gen_uuid
from app.core.config import settings
from app.constants import MODEL_GPT4O, MODEL_CLAUDE_SONNET

logger = logging.getLogger(__name__)

# Directory for browser artifacts
BROWSER_ARTIFACTS_DIR = os.path.join(os.getcwd(), "browser_artifacts")
os.makedirs(BROWSER_ARTIFACTS_DIR, exist_ok=True)

try:
    from browser_use import Agent, Browser
    from browser_use.llm import ChatOpenAI
    HAS_BROWSER_USE = True
except ImportError:
    HAS_BROWSER_USE = False
    Agent = object
    Browser = object
    ChatOpenAI = object


class BrowserService:
    _instance = None
    
    def __init__(self):
        self.browser = None
        # In v0.11+, Agent manages context/session, but we can pass a shared Browser instance
        if HAS_BROWSER_USE:
             self.browser = Browser(
                 headless=True,  # Default to headless for server
                 disable_security=True
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
            return "Error: browser-use library not installed or Python version incompatible."
            
        logger.info(f"Starting Browser Agent task: {task} (Session: {session_id})")
        

        logger.info(f"Using dynamic LLM for Browser Agent")
        
        # Initialize LLM using Factory (Dynamic)
        from app.core.llm.factory import LLMFactory
        llm = LLMFactory.create_llm()
        
        try:
            # Instantiate Agent
            # usage: Agent(task=..., llm=..., browser=...)
            agent = Agent(
                task=task,
                llm=llm,
                browser=self.browser,
                generate_gif=True
            )
            
            history = await agent.run()
            
            # Extract Result
            result_str = ""
            if history and hasattr(history, 'final_result'):
                 result_str = history.final_result()
            else:
                 result_str = str(history)

            # Handle GIF Artifacts
            # browser-use saves 'agent_history.gif' in CWD by default in v0.11?
            # We look for recent gifs in CWD.
            
            gifs = sorted(glob.glob("*.gif"), key=os.path.getmtime)
            if gifs:
                latest_gif = gifs[-1]
                # Move to static dir
                filename = f"browser_session_{gen_uuid()}.gif"
                dest_path = os.path.join(BROWSER_ARTIFACTS_DIR, filename)
                shutil.move(latest_gif, dest_path)
                
                # Construct URL
                base_url = settings.IMAGICBOX_API_URL or "http://localhost:8000"
                if not base_url.startswith("http"):
                     base_url = "http://localhost:8000"
                     
                # Assuming /static is mounted to BROWSER_ARTIFACTS_DIR or similar
                # For now just return the path relative/absolute or as markdown
                file_url = f"{base_url.rstrip('/')}/static/{filename}"
                result_str += f"\n\n![Browser Session]({file_url})"

            return result_str

        except Exception as e:
            logger.error(f"Browser Agent failed: {e}")
            return f"Browser Agent failed: {e}"

    async def close(self):
        if self.browser:
            await self.browser.close()

# Global instance
browser_service = BrowserService.get_instance()
