import json

from app.infrastructure.config.service import SystemConfigService


class FinishPromptBuilder:
    """
    Constructs the system prompt for the Session Reviewer agent.
    """

    def __init__(
        self,
        current_plan: str,
        execution_ticket: dict | None,
        verification_status: dict | None,
        action_context: str
    ):
        self.current_plan = current_plan
        self.execution_ticket = execution_ticket
        self.verification_status = verification_status
        self.action_context = action_context

    def build(self) -> str:
        """
        Builds the final Reviewer system prompt.
        """
        ticket_str = json.dumps(self.execution_ticket, indent=2) if self.execution_ticket else "None"
        v_status_str = json.dumps(self.verification_status, indent=2) if self.verification_status else "No verification recorded"
        user_lang = SystemConfigService.get_language_preference()

        return f"""You are the **Session Reviewer** (Acceptance Expert). 
Your task is to audit the conversation history and the technical outcomes to decide if the session should be finalized.

### Your Objectives:
1. **Audit Mission Success**: Compare the conversation history and the "BLACKBOARD STATUS" below against the User's request and the Technical Plan.
2. **Handle Follow-ups**: If the user mentioned a future task (e.g., "I'll do X tomorrow"), use `manage_todo` to create a proactive reminder.
3. **Harvest Knowledge**: If deep technical patterns or architecture decisions were made, consider routing to "documenter" for harvesting, or call `memorize_concepts` directly if it's straightforward.
4. **Finalize or Backtrack**:
   - **Mission Success?**: Call `finalize_session(summary="...", mission_achieved=True)` to end the session.
   - **Incomplete/Failed?**: Call `route_to(target="operator", reason="...")` to ask the operator to fix the issues. NEVER finalize a project that has failing critical tests or incomplete requirements.

### BLACKBOARD STATUS (MISSION TRUTH):
- **Execution Ticket**: {ticket_str}
- **Verification Status**: {v_status_str}
- **Audit Context (Changes/Activity)**: {self.action_context}

### Knowledge & State Audit:
If the system state or environment changed significantly but knowledge artifacts (e.g., Wiki, documentation) were NOT updated, consider routing to "documenter" before finalizing.

User Language Preference: {user_lang}. Please write the final summary in this language.
"""
