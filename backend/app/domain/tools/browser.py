from typing import Type, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig
import logging

from app.infrastructure.browser.agent import browser_service

logger = logging.getLogger(__name__)

class BrowserAgentInput(BaseModel):
    task: str = Field(description="The natural language task for the browser agent (e.g., 'Go to google.com and search for python', 'Login to X and post Y'). Be specific about steps if needed.")

class BrowserAgentTool(BaseTool):
    name: str = "browser_agent"
    description: str = "An autonomous browser agent that can navigate websites, interact with pages, fill forms, and extract data. Use this for complex web interaction tasks that regular search tools cannot handle (e.g. browsing SPAs, logging in, multi-step navigation)."
    args_schema: Type[BaseModel] = BrowserAgentInput
    
    def _run(self, task: str):
        raise NotImplementedError("Use _arun for async browser tasks")
        
    async def _arun(self, task: str, config: RunnableConfig = None):
        try:
            # Extract thread_id from config if available (LangGraph injects it)
            thread_id = None
            if config and 'configurable' in config:
                thread_id = config['configurable'].get('thread_id')
            
            return await browser_service.run_task(task, session_id=thread_id)
        except Exception as e:
            return f"Error running browser agent: {e}"

browser_agent = BrowserAgentTool()
