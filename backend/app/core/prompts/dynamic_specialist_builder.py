from typing import Any

from langchain_core.runnables import RunnableConfig

from app.core.engine.state import AgentConfig, ExecutionTicket


class DynamicSpecialistPromptBuilder:
    """
    Constructs the system prompt for dynamic, ephemeral sub-agents.
    """

    def __init__(self, agent_config: AgentConfig, ticket: ExecutionTicket):
        self.agent_config = agent_config
        self.ticket = ticket

    def build(self, config: RunnableConfig | None = None) -> str:
        """Constructs the full system prompt."""
        role_name = self.agent_config.get("role_name", "Specialist")
        instructions = self.agent_config.get("system_instructions", "You are a helpful assistant.")
        
        # Sandbox Warning
        sandbox_footer = self._build_sandbox_footer()

        return f"""## Your Role: {role_name}
{instructions}

## Constraints
- You are a specialized sub-agent.
- Your mission is defined in the Mission Ticket.
- Focus ONLY on the mission.
- Do not ask the user for clarification. If you are stuck, report the error.
- You are STATELESS. You do not remember previous interactions.

{sandbox_footer}
"""

    def build_mission_message(self) -> str:
        """Constructs the user message that initiates the task."""
        topic = self.ticket.get("topic") or "General Task"
        criteria = "\n".join([f"- {c}" for c in self.ticket.get("acceptance_criteria", [])])
        
        # Add parameter context if available
        params = self.ticket.get("parameters", {})
        param_context = ""
        if params:
            param_context = "\n**Execution Parameters**:\n" + "\n".join([f"- {k}: {v}" for k, v in params.items()])

        return f"""### MISSION TICKET
**Goal**: {topic}

**Acceptance Criteria**:
{criteria}
{param_context}

Please execute this mission now. Use your tools."""

    def _build_sandbox_footer(self) -> str:
        return """## SANDBOX PROTOCOL
- You have limited tools. Do not hallucinate tools you don't have.
- You cannot speak to the user.
- Provide a structured final report when done."""
