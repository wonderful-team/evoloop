import os
import sys
import asyncio
import logging
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI

# Add src to path just in case, though pip install should handle it
# sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from browser_use import Agent

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("browser_use_server")

mcp = FastMCP("Browser-Use Service")

@mcp.tool()
async def browse_web(task: str) -> str:
    """
    Control a web browser to perform a task.
    Args:
        task: The natural language description of the task (e.g. 'Go to google.com and search for EvoLoop').
    """
    logger.info(f"Received task: {task}")
    
    # Initialize LLM
    # We rely on standard OpenAI env vars: OPENAI_API_KEY, OPENAI_BASE_URL (optional)
    llm = ChatOpenAI(model="gpt-4o") # Use gpt-4o for best results with browser-use
    
    try:
        agent = Agent(
            task=task,
            llm=llm,
        )
        
        result = await agent.run()
        
        # Format result
        # result is AgentHistoryList usually? Or AgentOutput?
        # browser-use 0.11 return value:
        # It usually returns a history object. 
        # let's try to stringify it nicely.
        
        final_result = result.final_result()
        if final_result:
             return f"Task Completed. Result: {final_result}"
        
        return f"Task Completed. Trace: {result}"
        
    except Exception as e:
        logger.error(f"Error executing task: {e}")
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run(transport="sse")
