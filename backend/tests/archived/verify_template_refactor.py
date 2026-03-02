import asyncio
import os
import sys
from unittest.mock import MagicMock

# 1. TOTAL ISOLATION MOCKING (Must happen BEFORE any app imports)
# Mock the entire infrastructure and config landscape
mock_cfg = MagicMock()
mock_cfg.BRAIN_MEMORY_ROOT = "/tmp/evoloop_test"
mock_cfg.USE_NEO4J_MEMORY = False
mock_cfg.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
mock_cfg.REDIS_URL = "redis://localhost"

sys.modules["app.core.config"] = MagicMock(settings=mock_cfg)
sys.modules["app.infrastructure.database.redis"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()
sys.modules["redis.asyncio.connection"] = MagicMock()
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["app.infrastructure.database.session"] = MagicMock()

# Mock SystemConfigService BEFORE i18n
sys_cfg_svc = MagicMock()
sys_cfg_svc.get_language_preference.return_value = "en"
sys.modules["app.infrastructure.config.service"] = MagicMock(SystemConfigService=sys_cfg_svc)

# Mock i18n
mock_i18n = MagicMock()
mock_i18n.get.side_effect = lambda key: key
sys.modules["app.i18n.service"] = MagicMock(i18n=mock_i18n)

# Mock ToolManager
sys.modules["app.core.tools.manager"] = MagicMock()

# 2. Import the logic under test
sys.path.append(os.getcwd())

# We need to mock ContextManager BEFORE importing SupervisorPromptBuilder
# because the module itself might import something that uses it.
mock_cm = MagicMock()
sys.modules["app.core.context"] = MagicMock(ContextManager=mock_cm)
sys.modules["app.core.context.manager"] = MagicMock()

# Now we can safely import or just mock the data class
from app.core.context.manager import EvoContext
from app.core.engine.prompts import SupervisorPromptBuilder

async def verify_template_refactor():
    print("🚀 Verifying Template-Driven Architecture Refactor (Fully Isolated)...")
    
    # 1. Prep data
    os.makedirs("/tmp/evoloop_test/knowledge", exist_ok=True)
    os.makedirs("/tmp/evoloop_test/working", exist_ok=True)
    
    # 2. Setup Context
    ctx = EvoContext()
    ctx.environment_summaries = ["Connected to Test Lab"]
    ctx.memory_replay = ["Key Knowledge: python_testing"]
    ctx.active_boundaries = ["Constraint A"]
    ctx.metadata = {
        "has_android": True,
        "cwd": "/Users/test/project",
        "episodic_memory_raw": "Recent Learning: Jinja2 is powerful",
        "core_memory_raw": "Persistence is key",
        "user_preferences": {"language": "en"}
    }
    ctx.metadata = {
        "has_android": True,
        "cwd": "/Users/test/project",
        "episodic_memory_raw": "Recent Learning: Jinja2 is powerful",
        "core_memory_raw": "Persistence is key"
    }
    
    # 3. Setup Mock State for Builder
    mock_context = {
        "scratchpad": {
            "visited_nodes": ["operator"],
            "last_supervisor_route": "operator",
            "plan_approved": True,
            "route_reason": "Testing the refactor"
        },
        "structured_plan": {
            "title": "Refactor Plan",
            "steps": [
                {"title": "Step 1", "status": "done"},
                {"title": "Step 2", "status": "todo"}
            ]
        },
        "execution_ticket": {
            "ticket_type": "task",
            "focus_paths": ["main.py"],
            "acceptance_criteria": ["Logic is clean"]
        }
    }

    builder = SupervisorPromptBuilder(project_id=1, iteration_count=5, context=mock_context)
    
    # Ensure build() gets our mock context
    mock_cm.current.return_value = ctx

    # 4. Render
    prompt = builder.build(MagicMock())
    
    # 5. Assertions
    print("\n--- PROMPT OUTPUT START ---")
    print(prompt)
    print("--- PROMPT OUTPUT END ---\n")
    
    assertions = [
        ("Connected to Test Lab", "Environment Summary"),
        ("Key Knowledge: python_testing", "Memory Replay"),
        ("Constraint A", "Active Boundaries"),
        ("Rule 1", "Identity Rules"),
        ("Jinja2 is powerful", "Episodic Memory"),
        ("Persistence is key", "Core Memory"),
        ("ACTIVE TICKET: TASK", "Blackboard Ticket"),
        ("Testing the refactor", "Route Reason"),
        ("visited_nodes", "Loop Prevention (Visited Nodes)"),
        ("Refactor Plan", "Active Plan Title"),
        ("✅ Step 1", "Plan Step 1 Done"),
        ("⏳ Step 2", "Plan Step 2 Pending"),
        ("PASSED/APPROVED", "Plan Approved Status"),
        ("operating Android/Mobile", "Dynamic Platform Filter"),
    ]
    
    failed = False
    for text, label in assertions:
        if text in prompt:
            print(f"✅ PASSED: {label}")
        else:
            print(f"❌ FAILED: {label} (missing: '{text}')")
            failed = True
    
    if failed:
        sys.exit(1)

    print("\n🎉 Architectural shift verified successfully!")

if __name__ == "__main__":
    asyncio.run(verify_template_refactor())
