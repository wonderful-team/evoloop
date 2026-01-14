import asyncio
import os
import sys

# Ensure backend path is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


from app.core.config import settings
from app.core.workflows.evolution_graph import evolution_graph
from app.infrastructure.database.sql.database import session_scope
from app.infrastructure.database.sql.models.learning import TraceEvent


async def verify_evolution_trigger():
    print("🧬 Starting Evolution Loop Verification...")

    # 1. Seed Database with Failure Signals
    async with session_scope() as session:
        print("step 1: seeding database with failure signals...")

        # Cleanup first
        existing = await session.get(TraceEvent, 999999)
        if existing:
            await session.delete(existing)
            await session.flush()

        # create a fake trace event representing a meta-reviewer intervention
        fake_failure = TraceEvent(
            thread_id="test-evolution-thread",
            step_number=1,
            node_name="meta_reviewer",
            action_type="node_start",
            action_payload='{"error": "Simulated systemic failure"}',
            state_snapshot='{}', # Mock empty snapshot
            id=999999 # high id to avoid conflict
        )
        session.add(fake_failure)

    # 2. Run Evolution Graph
    print("step 2: running evolution graph...")
    inputs = {
        "project_id": 1,
        "messages": []
    }

    # We expect: SystemScanner -> EvolutionPlanner -> Coder -> ...
    # Since we are mocking, we just want to see if it correctly routes to Evolution Planner

    async for output in evolution_graph.astream(inputs):
        for node_name, state in output.items():
            print(f"  -> node executed: {node_name}")
            if node_name == "system_scanner":
                report = state.get("evolution_report")
                if report:
                    print(f"     [Report Generated]: {report[:100]}...")
                else:
                    print("     [Error] No report generated!")

            if node_name == "evolution_planner":
                print("     ✅ SUCCESS: Evolution Planner triggered!")
                # We can stop here to avoid actual coding
                return

    print("⚠️ Verification Ended without triggering Planner.")

if __name__ == "__main__":
    if not settings.ENABLE_SELF_EVOLUTION:
        settings.ENABLE_SELF_EVOLUTION = True # Force enable ENV for test

    # Enable Runtime Config in DB
    from app.domain.system.evolution_config import EvolutionConfigService
    EvolutionConfigService.set_enabled(True)

    asyncio.run(verify_evolution_trigger())
