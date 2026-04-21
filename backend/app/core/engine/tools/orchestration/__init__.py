"""
Orchestration & Control Tools - Phase 5 Architectural Consolidation

Re-exports from specialized sub-modules for backward compatibility.
New code should import directly from the sub-modules.
"""

# Schemas
from app.core.engine.tools.orchestration.schemas import (  # noqa: F401
    AggregateResult,
    DecomposeTaskResult,
    SpawnAgentsResult,
    ToolResult,
)

# Tools
from app.core.engine.tools.orchestration.parallelism import (  # noqa: F401
    aggregate_results,
    spawn_agents,
)
from app.core.engine.tools.orchestration.planning import decompose_task  # noqa: F401
from app.core.engine.tools.orchestration.routing import route_to  # noqa: F401
from app.core.engine.tools.orchestration.state_tools import manage_session_metadata  # noqa: F401
