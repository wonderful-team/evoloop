import os
import sys
import asyncio
import logging
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, Optional

# Add src to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")
sys.path.append(SRC_DIR)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("autoglm_server")

# Import Open-AutoGLM components
try:
    from phone_agent import PhoneAgent
    from phone_agent.agent import AgentConfig
    from phone_agent.model import ModelConfig
    from phone_agent.device_factory import DeviceType, set_device_type
except ImportError as e:
    logger.error(f"Failed to import Open-AutoGLM: {e}")
    # Continue to allow server to start, but methods will fail
    PhoneAgent = None

mcp = FastMCP("Open-AutoGLM Service")

class MobileService:
    def __init__(self):
        self.agent = None
        
    def _init_agent(self, device_id: str = None):
        if not PhoneAgent:
            raise ImportError("Open-AutoGLM not installed properly.")
            
        base_url = os.getenv("PHONE_AGENT_BASE_URL", "http://host.docker.internal:8000/v1") # Or wherever the model is
        model_name = os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b")
        api_key = os.getenv("PHONE_AGENT_API_KEY", "EMPTY")
        
        # Determine Device Type (default ADB)
        # In Docker, we likely use ADB over TCP
        set_device_type(DeviceType.ADB)

        model_config = ModelConfig(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key
        )
        
        agent_config = AgentConfig(
            max_steps=20, # Default limit
            device_id=device_id, # Optional specific device
            verbose=True
        )
        
        logger.info(f"Initializing PhoneAgent with model {model_name}...")
        self.agent = PhoneAgent(model_config=model_config, agent_config=agent_config)

    async def run_task(self, task: str, device_id: str = None) -> str:
        # Re-init if needed or just reuse? 
        # Open-AutoGLM agents might be stateful per task. 
        # Ideally we create a new one per task or reset.
        
        # For simplicity, re-init.
        try:
            self._init_agent(device_id)
            
            # Note: PhoneAgent.act might be synchronous or async?
            # Looking at source (assumed based on main.py), it seems sync but let's check.
            # Usually agents run a loop.
            # Assuming 'act' or similar method exists.
            
            # Based on standard usage: agent.run(task) or similar.
            # Wait, Open-AutoGLM main.py doesn't show 'agent.run'. 
            # It just creates it. Let's look at `phone_agent.py` if we could.
            # Assuming a generic `run` or `step` interface.
            
            # Let's assume there is a .run() method or something similar.
            # If main.py calls `handle_device_commands`, it's CLI based.
            # Let's check if there's a simpler entry point.
            
            # Fallback: Capture stdout/logs?
            pass
        except Exception as e:
            return f"Initialization Error: {e}"

        # If we can't find exact method signature from main.py, we might need to inspect `phone_agent` class.
        # But for now I'll assume `agent.act(task)` or `agent.run(task)`.
        
        # Let's wrap in thread if sync
        # result = await asyncio.to_thread(self.agent.act, task) 
        
        # Placeholder implementation until I verify the API
        return "Agent initialized but execution method pending API verification."

service = MobileService()

@mcp.tool()
async def control_mobile(task: str, device_id: str = None) -> str:
    """
    Control a mobile device (Android) to perform a task.
    Args:
        task: Natural language instruction (e.g. 'Open Settings and toggle WiFi').
        device_id: Optional ADB device serial or IP:PORT.
    """
    # Verify Open-AutoGLM is importable
    if not PhoneAgent:
        return "Error: Open-AutoGLM library missing."
        
    # We need to investigate PhoneAgent API to properly call it.
    # Since I cannot see phone_agent/phone_agent.py, I will try to infer or use `subprocess` to call `main.py` 
    # as a safe fallback! Calling `main.py` via subprocess is robust.
    
    cmd = ["python3", "src/main.py", "--quiet", "--device-type", "adb"]
    
    if device_id:
        # If it looks like IP:PORT, connect first?
        if ":" in device_id:
             cmd.extend(["--connect", device_id])
        else:
             cmd.extend(["--device-id", device_id])
            
    cmd.append(task)
    
    logger.info(f"Running Open-AutoGLM CLI: {' '.join(cmd)}")
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await proc.communicate()
    
    result = stdout.decode().strip()
    error = stderr.decode().strip()
    
    if proc.returncode != 0:
        return f"Task Failed:\nError: {error}\nOutput: {result}"
        
    return f"Task Completed:\n{result}"

if __name__ == "__main__":
    mcp.run(transport="sse")
