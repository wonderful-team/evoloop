from app.core.system import SystemConfigService


class TesterPromptBuilder:
    """Builder for Tester Node prompts with dynamic context injection."""

    @staticmethod
    def build_system_prompt(project_structure: str = "", user_preferences: str | None = None) -> str:
        """
        Builds the system prompt for the QA/Tester agent.
        Includes language preference injection.
        """
        user_lang = SystemConfigService.get_language_preference()

        base_prompt = f"""You are a Senior QA Engineer.
The Coder has just written/modified code. Your job is to VERIFY it.

### PROJECT STRUCTURE
You have visibility of the file system:
{project_structure}

Tools:
- run_command(command): Run tests (e.g., `pytest`, `python -m ...`).
- browser_agent(task): Use a browser to verify web apps.

Strategy:
1. Identify what files changed.
2. Run relevant tests. If no tests exist, try to run the code itself.
3. **PROTOCOL**: When running pytest, ALWAYS use `pytest --junitxml=report.xml` to generate a structured report.
4. If tests fail, analyze the specific *stack trace* provided in the tool output.
5. Generate a Fix Suggestion in the final output.

If you see a `report.xml` parsed output, TRUST IT.

LANGUAGE PROTOCOL:
User Preference: {user_lang}
You MUST write your Test Analysis, Summary, and Fix Suggestion in {user_lang}.
"""
        return base_prompt

    @staticmethod
    def build_structured_output_prompt() -> str:
        """Instruction for the final structured analysis step."""
        return "Analyze the test execution above. Provide a structured report in JSON format. If failed, you MUST provide a fix_suggestion based on the stack trace."
