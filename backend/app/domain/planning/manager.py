import json

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    title: str
    status: str = "pending"  # pending, in_progress, completed, failed
    details: str | None = None


class PlanDefinition(BaseModel):
    title: str
    steps: list[PlanStep] = Field(default_factory=list)


class PlanManager:
    @staticmethod
    def parse_plan_data(content: str) -> PlanDefinition | None:
        try:
            data = json.loads(content)
            return PlanDefinition(**data)
        except Exception:
            return None

    @staticmethod
    def format_plan_for_prompt(plan_json: str | None) -> str:
        if not plan_json:
            return "No plan yet."

        try:
            plan = PlanManager.parse_plan_data(plan_json)
            if not plan:
                return "Invalid Plan Data"

            steps_text = "\n".join([f"- {s.title} ({s.status})" for s in plan.steps])
            return f"Plan: {plan.title}\n{steps_text}"
        except Exception:
            return "Error parsing plan."

    @staticmethod
    def update_step_status(plan_json: str, step_index: int, status: str) -> str:
        """Updates a step status and returns new JSON string."""
        plan = PlanManager.parse_plan_data(plan_json)
        if plan and 0 <= step_index < len(plan.steps):
            plan.steps[step_index].status = status
            return plan.model_dump_json()
        return plan_json
