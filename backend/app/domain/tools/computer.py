from typing import Optional, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from app.infrastructure.computer.agent import computer_service

class ComputerAgentInput(BaseModel):
    instruction: str = Field(description="The natural language instruction for the computer to execute (e.g., 'Open Safari and search for Python').")

class ComputerAgentTool(BaseTool):
    name: str = "computer_agent"
    description: str = (
        "A multi-modal agent that can control the computer's mouse and keyboard to execute tasks. "
        "Use this for OS-level tasks like opening applications, managing windows, or performing complex GUI interactions that cannot be done via terminal. "
        "The agent takes a natural language instruction and executes it autonomously."
    )
    args_schema: Type[BaseModel] = ComputerAgentInput

    def _run(self, instruction: str) -> str:
        raise NotImplementedError("ComputerAgentTool only supports async execution.")

    async def _arun(self, instruction: str) -> str:
        try:
            return await computer_service.run_task(instruction)
        except Exception as e:
            return f"Error executing computer task: {e}"

computer_agent_tool = ComputerAgentTool()
