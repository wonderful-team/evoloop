from app.logging import logger
from langchain_core.messages import HumanMessage
from app.api.routes.agent import run_agent_background

async def handle_remote_command(command_data: dict):
    """
    Common handler for remote commands from EvoLoop Cloud.
    Can be used by both login.py (auto-connect) and main.py (startup recovery).
    """
    content = command_data.get("content", {})
    message = content.get("text") or content.get("message")
    
    if message:
        thread_id = command_data.get("thread_id") or "remote-default"
        logger.info(f"[EvoLoop] Executing remote command on thread {thread_id}: {message}")
        
        # Construct input state
        inputs = {
            "messages": [HumanMessage(content=message)],
            "project_id": 1, # Default project for now
            "command_id": command_data.get("command_id") # Pass command ID for tracking if needed
        }
        
        # Run agent in background
        await run_agent_background(thread_id, inputs)
