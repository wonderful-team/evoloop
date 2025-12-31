import logging
import sys
import os
import platform
import asyncio
from typing import Optional, Dict, Any
from app.utils.async_utils import run_in_thread

from app.core.config import settings

logger = logging.getLogger(__name__)

# Add Agent-S to sys.path
AGENT_S_PATH = os.path.abspath(os.path.join(os.getcwd(), "../../Agent-S"))
if AGENT_S_PATH not in sys.path:
    sys.path.append(AGENT_S_PATH)

HAS_AGENT_S = False
AgentS3 = object
OSWorldACI = object
LocalEnv = object

try:
    from gui_agents.s3.agents.agent_s import AgentS3
    from gui_agents.s3.agents.grounding import OSWorldACI
    from gui_agents.s3.utils.local_env import LocalEnv
    import pyautogui
    HAS_AGENT_S = True
except ImportError as e:
    logger.warning(f"Agent-S not found or missing dependencies: {e}")
    HAS_AGENT_S = False

class ComputerService:
    _instance = None
    
    def __init__(self):
        self.agent = None
        self.grounding_agent = None
        self._setup_agent()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _setup_agent(self):
        if not HAS_AGENT_S:
            return

        try:
            # Engine Params for Generation
            engine_params = {
                "engine_type": settings.OS_PROVIDER,
                "model": settings.OS_MODEL,
                "api_key": settings.OPENAI_API_KEY,
                # "base_url": ... if needed
            }

            # Engine Params for Grounding
            # OSWorldACI requires grounding_width/height matching the model
            ground_model = settings.OS_GROUND_MODEL
            if "ui-tars" in ground_model.lower():
                 w, h = (1920, 1080) # Default for 7B
                 if "72b" in ground_model.lower():
                     w, h = (1000, 1000)
            else:
                 w, h = (1920, 1080)

            engine_params_for_grounding = {
                "engine_type": settings.OS_GROUND_PROVIDER,
                "model": ground_model,
                "base_url": settings.OS_GROUND_URL,
                "api_key": settings.OS_GROUND_API_KEY or "empty",
                "grounding_width": w,
                "grounding_height": h,
            }

            # Sandbox / Local Env
            # For prototype, we disable local execution for safety unless configured
            local_env = None # LocalEnv() if settings.ENABLE_OS_EXECUTION else None

            self.grounding_agent = OSWorldACI(
                env=local_env,
                platform=platform.system().lower(),
                engine_params_for_generation=engine_params,
                engine_params_for_grounding=engine_params_for_grounding,
                width=w,
                height=h
            )

            self.agent = AgentS3(
                engine_params,
                self.grounding_agent,
                platform=platform.system().lower(),
                max_trajectory_length=8,
                enable_reflection=True
            )
            logger.info("Agent S3 initialized successfully.")

        except Exception as e:
            logger.error(f"Failed to initialize Agent S3: {e}")
            self.agent = None

    async def run_task(self, instruction: str) -> str:
        if not HAS_AGENT_S:
            return "Error: Agent-S library not found or dependencies missing (e.g. pyautogui, paddle)."
        
        if not self.agent:
            return "Error: Agent S3 failed to initialize (check logs for config/dependency errors)."

        if not settings.OS_GROUND_URL:
             return "Error: OS_GROUND_URL not configured. Agent S requires a grounding model (UI-TARS)."

        logger.info(f"Starting Computer Task: {instruction}")
        
        try:
            # Running synchronous agent code in a thread to avoid blocking loop
            result = await run_in_thread(self._run_agent_sync, instruction)
            return result
        except Exception as e:
            logger.error(f"Computer Agent failed: {e}")
            return f"Computer Agent failed: {e}"

    def _run_agent_sync(self, instruction: str) -> str:
        """
        Adapted from cli_app.py run_agent loop.
        Runs for a limited number of steps (e.g., 5) or until done.
        """
        import io
        from PIL import Image
        
        # Reset agent state
        self.agent.reset()
        
        # Determine screen size for scaling
        screen_width, screen_height = pyautogui.size()
        # Scale logic from cli_app
        max_dim = 2400
        scale_factor = min(max_dim / screen_width, max_dim / screen_height, 1)
        scaled_width = int(screen_width * scale_factor)
        scaled_height = int(screen_height * scale_factor)
        
        traj_log = []
        obs = {}
        
        MAX_STEPS = 5 # Limit steps for safety/latency in this prototype
        
        for step in range(MAX_STEPS):
             # Screenshot
             screenshot = pyautogui.screenshot()
             screenshot = screenshot.resize((scaled_width, scaled_height), Image.LANCZOS)
             buffered = io.BytesIO()
             screenshot.save(buffered, format="PNG")
             obs["screenshot"] = buffered.getvalue()
             
             logger.info(f"Step {step+1}: Predicting action...")
             
             # Predict
             # agent.predict returns (info, code_list)
             info, code = self.agent.predict(instruction=instruction, observation=obs)
             
             action_code = code[0]
             traj_log.append(f"Step {step+1}: {action_code}")
             
             if "done" in action_code.lower() or "fail" in action_code.lower():
                 return f"Task Finished: {action_code}\nLog:\n" + "\n".join(traj_log)
                 
             if "wait" in action_code.lower():
                 # time.sleep(5) inside executor
                 pass
                 
             # Executing code - DANGEROUS implies full computer control
             # For now, we EXECUTE it because that's the point of the agent
             # But we should wrap it carefully
             
             logger.info(f"Executing: {action_code}")
             try:
                 # Evaluate/Exec the code (mostly pyautogui calls)
                 exec(action_code) 
             except Exception as exec_err:
                 traj_log.append(f"Execution Error: {exec_err}")
                 return f"Execution failed at step {step+1}: {exec_err}\nLog:\n" + "\n".join(traj_log)

        return "Task reached max steps (5).\nLog:\n" + "\n".join(traj_log)

# Global instance
computer_service = ComputerService.get_instance()
