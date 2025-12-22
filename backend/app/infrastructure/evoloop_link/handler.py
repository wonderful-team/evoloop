from app.logging import logger
from langchain_core.messages import HumanMessage

async def handle_remote_command(command_data: dict):
    """
    Common handler for remote commands from EvoLoop Cloud.
    Can be used by both login.py (auto-connect) and main.py (startup recovery).
    """
    # Import inside function to avoid circular dependency
    # agent.py imports get_evoloop_client which is in client.py
    # client.py imports nothing, but main.py sets up everything.
    # If handler is imported at top level in main, it's fine.
    # But if handler depends on agent, and agent depends on client (which might use handler type hint), it can be tricky.
    # The error "No module named 'core'" suggests a deeper issue or misconfiguration in execution context,
    # but based on the code structure, agent.py <-> infrastructure/evoloop_link is a likely cycle.
    # Let's lazy import run_agent_background.
    from app.api.routes.agent import run_agent_background

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
