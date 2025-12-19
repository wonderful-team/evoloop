from typing import Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
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
        
    async def _arun(self, task: str):
        try:
            return await browser_service.run_task(task)
        except Exception as e:
            return f"Error running browser agent: {e}"

browser_agent = BrowserAgentTool()
