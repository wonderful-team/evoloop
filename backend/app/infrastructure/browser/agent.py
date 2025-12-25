import logging
import asyncio
import os
import uuid
from typing import Optional, Dict

from langchain_openai import ChatOpenAI
# from langchain_anthropic import ChatAnthropic # Optional: if using Claude

try:
    from browser_use import Agent
    from browser_use.browser.browser import Browser, BrowserConfig
    from browser_use.browser.context import BrowserContext, BrowserContextConfig
    HAS_BROWSER_USE = True
except ImportError:
    HAS_BROWSER_USE = False
    BrowserContext = object # or Any
    Browser = object


from app.core.config import settings

logger = logging.getLogger(__name__)

# Directory for browser artifacts
BROWSER_ARTIFACTS_DIR = os.path.join(os.getcwd(), "browser_artifacts")
os.makedirs(BROWSER_ARTIFACTS_DIR, exist_ok=True)

class BrowserService:
    _instance = None
    
    def __init__(self):
        self.browser = None
        self.session_contexts: Dict[str, BrowserContext] = {}

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
    
    async def get_context(self, session_id: str = None) -> BrowserContext:
        """
        Get or create a browser context for a session.
        """
        if not self.browser:
            raise RuntimeError("Browser not initialized")

        if session_id:
            if session_id in self.session_contexts:
                return self.session_contexts[session_id]
            
            # Create new persistent context
            # Note: browser-use 0.x might not have save_cookies readily available in ContextConfig 
            # without a specific path, but let's try to pass a persistent user data dir if supported
            # or just keep it in memory (which persists as long as server runs).
            context = await self.browser.new_context(
                config=BrowserContextConfig(
                    # save_recording_path=BROWSER_ARTIFACTS_DIR, # If supported
                )
            )
            self.session_contexts[session_id] = context
            return context
        else:
            # Ephemeral context
            return await self.browser.new_context()

    async def run_task(self, task: str, session_id: str = None) -> str:
        """
        Run a browser task using browser-use Agent.
        """
        if not HAS_BROWSER_USE:
            return "Error: browser-use library not installed or Python version incompatible (requires >=3.11)."
            
        logger.info(f"Starting Browser Agent task: {task} (Session: {session_id})")
        
        # Initialize LLM
        # browser-use requires a powerful model (GPT-4o or Claude 3.5 Sonnet).
        # We prioritize a specific BROWSER_MODEL_NAME setting, then fallback to OPENAI_MODEL_NAME if capable, 
        # or default to gpt-4o.
        
        # Check if we have a specific browser model setting (needs to be added to config, or we just look in env)
        model_name = os.getenv("BROWSER_MODEL_NAME")
        if not model_name:
            # If global model is strong, use it. Otherwise default to gpt-4o.
            global_model = settings.OPENAI_MODEL_NAME
            if global_model in ["gpt-4o", "claude-3-5-sonnet-20240620"]:
                model_name = global_model
            else:
                model_name = "gpt-4o"
        
        api_key = settings.OPENAI_API_KEY
        # Support for other providers could be added here (e.g. Anthropic)
        
        if not api_key:
            return "Error: OPENAI_API_KEY not configured."
            
        logger.info(f"Using model {model_name} for Browser Agent")
        llm = ChatOpenAI(model=model_name, api_key=api_key)
        
        try:
            # reuse or create context
            context = await self.get_context(session_id)
            
            # Agent
            agent = Agent(
                task=task,
                llm=llm,
                browser_context=context,
                generate_gif=True 
            )
            
            history = await agent.run()
            
            # Close context if ephemeral
            if not session_id:
                await context.close()

            # Extract Result
            result_str = ""
            if history and hasattr(history, 'final_result'):
                 result_str = history.final_result()
            else:
                 result_str = str(history)

            # Find generated GIF
            # browser-use saves 'agent_history.gif' (or similar) in the current working directory 
            # or context directory. 
            # We need to find the latest gif in cwd or BROWSER_ARTIFACTS_DIR if we configured it.
            # For now, let's assume it saves to CWD named 'agent_history.gif' and we move it.
            # Ideally browser-use allows configuring output path per run. 
            # If not, we scan for commonly named files.
            
            import shutil
            import glob
            
            # Look for recent GIFs
            gifs = sorted(glob.glob("*.gif"), key=os.path.getmtime)
            if gifs:
                latest_gif = gifs[-1]
                # Move to static dir
                filename = f"browser_session_{uuid.uuid4()}.gif"
                dest_path = os.path.join(BROWSER_ARTIFACTS_DIR, filename)
                shutil.move(latest_gif, dest_path)
                
                # Append URL to result
                # URL is /static/filename
                # Using Markdown image syntax
                
                # Base URL handling? We can use relative path if frontend supports it, 
                # or we need the backend base URL.
                # Let's use relative path for now: /api/v1/static/... or just /static/...
                # But frontend runs on different port/domain usually?
                # If EvoLoop is monolithic or proxied, /static works.
                # If mobile app, it needs full URL.
                # We can try to prepend generic base url or just return relative.
                # Let's try to get base url from settings.
                base_url = settings.EVOLOOP_LINK_BASE_URL or "http://localhost:8000"
                if not base_url.startswith("http"):
                     base_url = "http://localhost:8000" # Fallback
                     
                file_url = f"{base_url.rstrip('/')}/static/{filename}"
                result_str += f"\n\n![Browser Session]({file_url})"

            return result_str

        except Exception as e:
            logger.error(f"Browser Agent failed: {e}")
            return f"Browser Agent failed: {e}"

    async def close(self):
        # Close all contexts
        for ctx in self.session_contexts.values():
            await ctx.close()
        
        if self.browser:
            await self.browser.close()

# Global instance
browser_service = BrowserService.get_instance()
