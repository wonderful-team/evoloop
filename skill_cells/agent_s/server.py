import os
import sys
import asyncio
import logging
import platform
import io
import base64
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any, List

# Add src to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")
sys.path.append(SRC_DIR)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_s_server")

# Import Agent-S components
try:
    from gui_agents.s3.agents.agent_s import AgentS3
    from gui_agents.s3.agents.grounding import OSWorldACI
    import pyautogui
except ImportError as e:
    logger.error(f"Failed to import Agent-S: {e}")
    sys.exit(1)

# Initialize MCP Server
mcp = FastMCP("Agent-S Service")

class AgentService:
    def __init__(self):
        self.agent = None
        self.grounding_agent = None
        self._init_agent()

    def _init_agent(self):
        # Load config from Environment Variables
        os_provider = os.getenv("OS_PROVIDER", "openai")
        os_model = os.getenv("OS_MODEL", "gpt-4o")
        os_api_key = os.getenv("OPENAI_API_KEY")
        
        ground_provider = os.getenv("OS_GROUND_PROVIDER", "huggingface")
        ground_model = os.getenv("OS_GROUND_MODEL", "ui-tars-1.5-7b")
        ground_url = os.getenv("OS_GROUND_URL", "http://localhost:8080")
        ground_api_key = os.getenv("OS_GROUND_API_KEY", "empty")

        engine_params = {
            "engine_type": os_provider,
            "model": os_model,
            "api_key": os_api_key,
        }

        # Screen dimensions (Default 1920x1080 for 7B model coverage)
        w, h = (1920, 1080)
        # If running inside Xvfb docker, we should match this.

        engine_params_for_grounding = {
            "engine_type": ground_provider,
            "model": ground_model,
            "base_url": ground_url,
            "api_key": ground_api_key,
            "grounding_width": w,
            "grounding_height": h,
        }

        logger.info("Initializing AgentS3...")
        try:
            self.grounding_agent = OSWorldACI(
                env=None, # No local env sandbox yet, direct execution
                platform="linux", # Docker is linux
                engine_params_for_generation=engine_params,
                engine_params_for_grounding=engine_params_for_grounding,
                width=w,
                height=h
            )

            self.agent = AgentS3(
                engine_params,
                self.grounding_agent,
                platform="linux",
                max_trajectory_length=5, # Limit steps per turn
                enable_reflection=True
            )
            logger.info("AgentS3 initialized successfully.")
        except Exception as e:
            logger.error(f"Validation Error during Init: {e}")
            # Don't crash yet, retry on request?
            
    def run_instruction(self, instruction: str) -> str:
        if not self.agent:
            self._init_agent()
            if not self.agent:
                return "Error: Agent is not initialized."

        logger.info(f"Processing instruction: {instruction}")
        
        # Reset Logic
        self.agent.reset()
        
        obs = {}
        traj_log = []
        
        # Capture initial screenshot
        try:
            # PyAutoGUI in Xvfb
            screenshot = pyautogui.screenshot()
            # Resize? logic from original wrapper
            # For strict grounding, we should keep aspect ratio or match model expected size
            # Assuming 1920x1080 in docker
            
            buffered = io.BytesIO()
            screenshot.save(buffered, format="PNG")
            obs["screenshot"] = buffered.getvalue()
        except Exception as e:
            return f"Error capturing screenshot: {e}"

        # Standard Step Loop (Single Turn or Multi Turn?)
        # For MCP tool, we might want to run the whole task (max 5 steps) and return log.
        
        MAX_STEPS = 5
        for step in range(MAX_STEPS):
             logger.info(f"Step {step+1}...")
             
             # Prediction
             try:
                 info, code = self.agent.predict(instruction=instruction, observation=obs)
             except Exception as e:
                 return f"Error during prediction: {e}\nLog: {traj_log}"

             action_code = code[0] if code else "pass"
             traj_log.append(f"Action {step+1}: {action_code}")
             
             if "done" in action_code.lower() or "fail" in action_code.lower():
                 break
                 
             # Execute
             try:
                 # Dangerous: Direct Exec
                 # In Docker this is safer
                 exec(action_code)
             except Exception as e:
                 traj_log.append(f"Execution Error: {e}")
                 break
                 
             # Update Observation
             screenshot = pyautogui.screenshot()
             buffered = io.BytesIO()
             screenshot.save(buffered, format="PNG")
             obs["screenshot"] = buffered.getvalue()
             
        return "\n".join(traj_log)

service = AgentService()

@mcp.tool()
def computer_execute(instruction: str) -> str:
    """
    Execute a computer control task using Agent-S.
    Args:
        instruction: Natural language instruction (e.g. 'Open browser and search for X').
    """
    return service.run_instruction(instruction)

if __name__ == "__main__":
    # Run as SSE by default on port 8000, visible to Docker network
    # We must explicitly set host to 0.0.0.0
    from mcp.server.fastmcp import Context
    
    # Note: FastMCP run() signature varies by version, but assuming generic support
    # If not supported, we might need: mcp.settings.host = "0.0.0.0"
    # Or just rely on standard env vars if mcp library supports them.
    # For now, let's try explicit args if allowed, or fallback to uvicorn invocation if mcp exposes app.
    
    # Safest: Use mcp.run with explicit kwargs if library supports it, or standard uvicorn 
    # if mcp is based on FastAPI.
    # Looking at imports: `from mcp.server.fastmcp import FastMCP`
    # Common pattern:
    import uvicorn
    # mcp.run(transport='sse') usually starts uvicorn. 
    # Let's use direct uvicorn to receive the ASGI app if accessible, 
    # OR assume mcp.run takes host/port. 
    
    # Given I cannot check docs, I will use `mcp.run(transport="sse")` and set env vars 
    # UVICORN_HOST / UVICORN_PORT if possible?
    
    # Let's try passing host/port to run().
    mcp.run(transport="sse")
