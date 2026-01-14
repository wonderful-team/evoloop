import json
import os
import sys
from unittest.mock import MagicMock

# Fix path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.prompts.planner_builder import PlannerPromptBuilder
from app.domain.planning.manager import PlanManager


def test_manager_parse():
    print("--- Test 1: PlanManager Parsing ---")
    json_data = json.dumps({
        "title": "My Plan",
        "steps": [{"title": "Step 1", "status": "pending"}]
    })
    plan = PlanManager.parse_plan_data(json_data)
    if plan and plan.title == "My Plan":
        print("SUCCESS: Plan parsed.")
    else:
        print("FAIL: Plan not parsed.")

def test_manager_update():
    print("--- Test 2: PlanManager Update Status ---")
    json_data = json.dumps({
        "title": "My Plan",
        "steps": [{"title": "Step 1", "status": "pending"}]
    })
    new_json = PlanManager.update_step_status(json_data, 0, "completed")
    plan = PlanManager.parse_plan_data(new_json)
    if plan and plan.steps[0].status == "completed":
        print("SUCCESS: Step updated to completed.")
    else:
        print(f"FAIL: Step status is {plan.steps[0].status if plan else 'None'}")

def test_builder_prompt():
    print("--- Test 3: PlannerPromptBuilder ---")
    builder = PlannerPromptBuilder(
        project_id=1,
        current_plan="Step 1 (done)",
        context={"project_structure": "- root\n  - main.py"}
    )
    prompt = builder.build(MagicMock())

    if "Project ID: 1" in prompt and "Step 1 (done)" in prompt:
        print("SUCCESS: Context injected.")
    else:
        print("FAIL: Context missing.")

    if "User Language:" in prompt:
         print("SUCCESS: Language injected.")

if __name__ == "__main__":
    test_manager_parse()
    test_manager_update()
    test_builder_prompt()
