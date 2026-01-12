import platform

from langchain_core.runnables import RunnableConfig

from app.core.tools.base import get_working_directory
from app.domain.system.service import SystemConfigService


class PlannerPromptBuilder:
    def __init__(self, project_id: int, current_plan: str, context: dict | None = None):
        self.project_id = project_id
        self.current_plan = current_plan
        self.context = context or {}

    def build(self, config: RunnableConfig) -> str:
        """Constructs the system prompt dynamically."""
        user_lang = self._get_user_language()
        sys_info = self._get_system_info(config)

        return f"""You are the **Lead Architect** (Planner) of the system.

**Your Goal**: Analyze the user's request and the current project context to create a robust, step-by-step **Implementation Plan**.

**Context**:
Project ID: {self.project_id}
Current Plan: {self.current_plan}
System Info: {sys_info}
Past Experience:
{self.context.get('past_experience', 'No relevant history found.')}

**Responsibilities**:
1. **Analyze**: Understand the user's goal. If unsure, you can verify context, but your main output is a PLAN.
2. **Breakdown**: Split the task into atomic, verifiable steps.
   - Good steps: "Create `api.py`", "Implement `login` function", "Add unit tests".
   - Bad steps: "Do it", "Code functionality".
3. **Verify Feasibility**: The plan must be technically grounded.
4. **Feasibility Check**: You MUST call `analyze_feasibility` on your proposed plan before finalizing it.

**Tools Available**:
- `create_plan(title, steps)`: To create a NEW plan.
- `update_step_status(step_index, status)`: To mark progress (if plan exists).
- `analyze_feasibility(proposed_plan)`: To check for risks.

**Output Protocol**:
- If a plan already exists but is outdated/failed, UPDATE it or CREATE a new one.
- If no plan exists, CREATE one.
- Once the plan is created and saved (via tool), output "Plan created. Handing off to Supervisor."

**Language**:
- User Language: {user_lang}
- Write plan titles and steps in {user_lang}.
"""

    def _get_user_language(self) -> str:
        return SystemConfigService.get_language_preference()

    def _get_system_info(self, config: RunnableConfig) -> str:
        cwd = get_working_directory(config)
        # We could inject tree structure here if we want to be fancy,
        # but for now let's keep it lightweight or assume the node injects it via 'context'
        # if the builder is responsible, we should do it here.

        # Let's try to get tree if key is present in context, else generate
        project_structure = self.context.get("project_structure", "Tree not available")

        return f"OS: {platform.system()}, CWD: {cwd}\nProject Structure:\n{project_structure}"
