
import json
import logging
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from app.core.llm.factory import get_default_llm
from app.infrastructure.evoloop_link.client import get_evoloop_client

logger = logging.getLogger(__name__)

@tool
def decompose_requirements(requirements: str) -> str:
    """
    Analyze requirements text and decompose it into a list of technical tasks.
    Returns a JSON string containing the list of tasks.
    
    Args:
        requirements (str): The requirements text, document content, or user instruction.
    """
    try:
        llm = get_default_llm()
        
        system_prompt = """You are a Senior Technical Project Manager and Architect.
Your goal is to decompose the given requirements into specific, actionable technical tasks.

Current Context:
Target System: Member Center Project Management (NiuShop based)

For each task, you MUST provide:
1. task_title: Clear and concise.
2. task_desc: Detailed description including acceptance criteria.
3. priority: 1 (Low), 2 (Medium), 3 (High), 4 (Urgent).
4. implementation_complexity: 'low', 'medium', 'high'.
5. skills_required: List of strings (e.g., ["PHP", "Vue3"]).
6. technical_challenges: List of strings (potential blockers).
7. match_score: 0-100 (Relevance confidence).

Output Format:
Return ONLY a JSON array of task objects. Example:
[
  {
    "task_title": "Implement Login API",
    "task_desc": "Create strict login controller...",
    "priority": 3,
    "implementation_complexity": "medium",
    "skills_required": ["PHP", "Redis"],
    "technical_challenges": ["Concurrency"],
    "match_score": 95
  }
]
"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{requirements}")
        ])
        
        chain = prompt | llm | JsonOutputParser()
        
        result = chain.invoke({"requirements": requirements})
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        logger.error(f"Decomposition failed: {e}")
        return json.dumps({"error": str(e)})

@tool
def create_project_task(project_id: int, task_data: str) -> str:
    """
    Create a task in the remote project management system via EvoLoop Link.
    
    Args:
        project_id (int): The ID of the project to add the task to.
        task_data (str): JSON string representation of the task data (title, desc, priority, etc.).
    """
    try:
        client = get_evoloop_client()
        if not client:
            return "Error: EvoLoop Link Client not initialized or connected."

        # Parse task data if it's a string
        if isinstance(task_data, str):
            try:
                task_dict = json.loads(task_data)
            except json.JSONDecodeError:
                return "Error: task_data is not valid JSON."
        else:
            task_dict = task_data

        # Ensure project_id is set
        task_dict['project_id'] = project_id
        
        # We need to call the remote API
        # Since client._api_request is internal/async, and tools are often sync, 
        # we strictly need to run this async or wrap it. 
        # However, EvoLoop tools seem to be sync functions mostly?
        # Let's check if we can run async. 
        # LangChain supports async tools. But client._api_request is async.
        # For now we assume this tool runs in an async context or we use async_to_sync.
        
        # Hack: Start a temporary loop if strictly sync, but better to make tool async def.
        # But wait, `decompose_requirements` is sync.
        # Let's define this as async only if the agent supports it.
        # Re-checking standard EvoLoop tools, most seem sync.
        # But EvoLoopLinkClient methods are async.
        
        import asyncio
        
        # API Endpoint: /projectmanage/api/task/create
        # Note: The client methods like _api_request are protected. 
        # Ideally we should extend the client or use public methods.
        # But Python access allows protected call.
        
        async def _do_create():
            return await client._api_request(
                "POST", 
                "/projectmanage/api/task/create",
                task_dict
            )
            
        # Run async in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            # If we are already in an event loop (e.g. FastAPI), we can't block.
            # This is tricky for a Sync tool.
            # Ideally the tool should be async.
            # For this implementations sake, assuming we can return a coroutine if using LangGraph async.
            # But standard @tool decorator handles sync/async.
            
            # Let's try to just return "Please use async runner" if failed?
            # No, let's look at `create_project_task` below.
            pass

        # Correct approach for sync wrapper of async library:
        # If loop is running, we might need `nest_asyncio` or simply define tool as `async def`.
        # Converting this function to `async def` is the safest bet for LangChain.
        pass

    except Exception as e:
        return f"Error preparing task creation: {str(e)}"
        
    return "Error: Implementation of async bridge pending. Ideally define as async tool."
    
# Re-define as Async Tool properly
@tool
async def create_project_task_async(project_id: int, task_data: str) -> str:
    """
    Create a task in the remote project management system via EvoLoop Link.
    Async version.
    
    Args:
        project_id (int): The ID of the project to add the task to.
        task_data (str): JSON string representation of the task data.
    """
    try:
        client = get_evoloop_client()
        if not client:
            return "Error: EvoLoop Link Client not initialized."
            
        if isinstance(task_data, str):
            task_dict = json.loads(task_data)
        else:
            task_dict = task_data
            
        task_dict['project_id'] = project_id
        
        # Endpoint: /projectmanage/api/task/create
        # We need to construct the params expected by `Task.create` in PHP:
        # project_id, task_title, task_desc, priority, ...
        # The schema from `decompose_requirements` matches this.
        
        response = await client._api_request(
            "POST", 
            "/projectmanage/api/task/create",
            task_dict
        )
        
        if response.get("code") == 0:
            return f"Success: Task created with ID {response.get('data', {}).get('task_id')}"
        else:
            return f"Failed: {response.get('message')}"
            
    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        return f"Error: {str(e)}"
