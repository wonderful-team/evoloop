import json


class FinishPromptBuilder:
    """
    Constructs the system prompt for the Finish Node's session analysis.
    """
    
    def __init__(
        self,
        user_lang: str,
        current_plan: str,
        tool_summary: str,
        execution_ticket: dict | None,
        test_results: dict | None,
        git_context: str
    ):
        self.user_lang = user_lang
        self.current_plan = current_plan
        self.tool_summary = tool_summary
        self.execution_ticket = execution_ticket
        self.test_results = test_results
        self.git_context = git_context

    def build(self) -> str:
        """
        Builds the final prompt string.
        """
        ticket_str = json.dumps(self.execution_ticket, indent=2) if self.execution_ticket else "None"
        tests_str = json.dumps(self.test_results, indent=2) if self.test_results else "No tests recorded"
        
        plan_str = self.current_plan[:1000] if self.current_plan else "No formal plan"

        return f"""You are the EvoLoop Session Analyst.
The user's task has been completed. Analyze the conversation and provide a structured conclusion.

**User Language Preference**: {self.user_lang}

**Task Plan (if any)**: {plan_str}

**Tools Used**: {self.tool_summary}

**BLACKBOARD STATUS (MISSION TRUTH)**:
Active Ticket: {ticket_str}
Verification Status: {tests_str}

{self.git_context}

### Instructions

1. **summary**: Write a concise, professional summary of what was accomplished.
   - Use the user's preferred language ({self.user_lang})
   - **IMPORTANT**: Use the BLACKBOARD STATUS above as the primary evidence of success. 
   - If tests are "verified", state this clearly as a proven outcome.
   - Mention key actions taken and outcomes.
   - Use Markdown formatting with bullet points if appropriate.

2. **harvested_concepts**: Extract up to 5 concepts worth remembering:
   - Technologies, patterns, or architecture decisions used in the ticket mission.
   - Domain-specific terms or configurations.
   - NOT generic programming terms (like "function", "variable").
   - Each concept needs a name and description.

3. **proactive_todo**: If the conversation mentioned any follow-up tasks:
   - "I'll deploy this later", "Check the logs in 30 minutes", etc.
   - Set should_create=true only if a real action is needed later
   - Ignore completed tasks or generic statements

Analyze the conversation and respond with the SessionConclusion structure.
"""
