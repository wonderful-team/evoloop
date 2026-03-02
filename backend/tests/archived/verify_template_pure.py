import asyncio
import os
import sys
from jinja2 import Environment, FileSystemLoader

async def verify_template_logic():
    print("🚀 Verifying Prompt Template Logic (Pure Rendering)...")
    
    template_dir = "evoloop/backend/app/core/engine/prompts/templates"
    if not os.path.exists(template_dir):
        # Fallback for different working directories
        template_dir = "app/core/engine/prompts/templates"
    
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("supervisor.prompt.j2")
    
    # Setup test variables (Mirroring SupervisorPromptBuilder.build())
    template_vars = {
        "project_id": 1,
        "iteration_count": 5,
        "environment": {
            "summaries": ["Connected to Test Lab"],
            "memory_replay": ["Key Knowledge: python_testing"],
            "boundaries": ["Constraint A: No iOS"],
            "user_preferences": {"language": "en", "theme": "dark"},
            "mcp_inventory": "Active MCP: filesystem, search",
        },
        "blackboard": {
            "ticket": {
                "ticket_type": "feature",
                "focus_paths": ["main.py", "utils.py"],
                "acceptance_criteria": ["Logic is clean", "Tests pass"],
            },
            "verification": {"status": "verified"},
            "route_reason": "Implementing core logic",
        },
        "memory": {
            "episodic_raw": "Recent Learning: Jinja2 is powerful",
            "core_raw": "Persistence is key",
            "use_neo4j": False,
        },
        "plan": {
            "title": "Refactor Plan",
            "steps": [
                {"title": "Step 1", "status": "done"},
                {"title": "Step 2", "status": "todo"}
            ]
        },
        "plan_approved": True,
        "warnings": {
            "visited_nodes": ["operator", "deep_researcher"],
            "last_route": "operator",
            "is_ambiguous": False,
            "last_human_msg": "Long enough message",
        },
        "sys_info": {
            "project_structure": "CWD: /Users/test/project\n(Tree structure...)",
            "project_concepts": "\nRelevant concepts: python_coding",
        },
        "has_android": True,
        "has_macos": False,
    }

    prompt = template.render(**template_vars)
    
    print("\n--- RENDERED PROMPT START ---")
    print(prompt)
    print("--- RENDERED PROMPT END ---\n")
    
    assertions = [
        ("Connected to Test Lab", "Environment Summary"),
        ("Key Knowledge: python_testing", "Memory Replay"),
        ("Constraint A: No iOS", "Active Boundaries"),
        ("NEVER delete .git", "System Safety Rules"),
        ("Jinja2 is powerful", "Episodic Memory"),
        ("Persistence is key", "Core Memory"),
        ("ACTIVE TICKET: FEATURE", "Blackboard Ticket Type"),
        ("main.py, utils.py", "Focus Paths"),
        ("Logic is clean", "Acceptance Criteria"),
        ("Implementing core logic", "Route Reason"),
        ("verified", "Verification Status"),
        ("You just routed to: **operator**", "Loop Prevention (Last Route)"),
        ("Nodes visited this session: operator, deep_researcher", "Loop Prevention (Visited Nodes)"),
        ("Refactor Plan", "Active Plan Title"),
        ("1. ✅ Step 1", "Plan Step 1 Done"),
        ("2. ⏳ Step 2", "Plan Step 2 Pending"),
        ("PASSED/APPROVED", "Plan Approved Status"),
        ("operating Android/Mobile", "Dynamic Platform Filter"),
    ]
    
    failed = False
    for text, label in assertions:
        if text.lower() in prompt.lower():
            print(f"✅ PASSED: {label}")
        else:
            print(f"❌ FAILED: {label} (missing: '{text}')")
            failed = True
    
    if failed:
        sys.exit(1)

    print("\n🎉 Template logic verified successfully!")

if __name__ == "__main__":
    asyncio.run(verify_template_logic())
