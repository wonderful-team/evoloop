from typing import Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.mobile.agent import mobile_service


class MobileAgentInput(BaseModel):
    instruction: str = Field(description="The natural language instruction for the mobile phone to execute (e.g., 'Open WeChat and send a message').")


class MobileAgentTool(BaseTool):
    name: str = "mobile_agent"
    description: str = (
        "A multi-modal agent that can control an Android device connected via ADB or HDC. "
        "Use this for mobile-specific tasks like testing apps, sending navigating mobile GUIs. "
        "The agent takes a natural language instruction and executes it autonomously."
    )
    args_schema: Type[BaseModel] = MobileAgentInput

    def _run(self, instruction: str) -> str:
        raise NotImplementedError("MobileAgentTool only supports async execution.")

    async def _arun(self, instruction: str) -> str:
        try:
            return await mobile_service.run_task(instruction)
        except Exception as e:
            return f"Error executing mobile task: {e}"


mobile_agent_tool = MobileAgentTool()
