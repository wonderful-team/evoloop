"""Memory subsystem constants.

Centralizes tuning knobs and default limits for the memory module so they are
not buried in class bodies or function signatures.

Operational config values (e.g. MEMORY_SEARCH_LIMIT) live in ``app.core.config``;
this module exposes the memory-facing defaults derived from or aligned with them.
"""

from app.core.config import settings

#: 遗忘安全窗口：只能遗忘超过 N 步的工具输出。
FORGET_SAFETY_WINDOW = 5

# ====================== Search / Retrieval Defaults ======================
#: Default number of memory results returned by search/list interfaces.
DEFAULT_SEARCH_LIMIT: int = settings.MEMORY_SEARCH_LIMIT

#: Stage-1 candidate pool size for smart retrieval.
DEFAULT_RETRIEVAL_CANDIDATES = 20
#: Stage-2 final result count for smart retrieval.
DEFAULT_RETRIEVAL_RESULTS = 5

#: High-confidence skip threshold for stage-2 LLM selection.
SELECTION_SKIP_THRESHOLD = 5.0

# ====================== Quality Analysis ======================
#: Overall quality score below which a memory is considered low quality.
QUALITY_THRESHOLD = 0.4
#: Freshness half-life (days) used in exponential decay.
FRESHNESS_HALF_LIFE = 30

# ====================== Maintenance / Pruning ======================
#: Library scale at which pruning/consolidation is triggered.
MAINTENANCE_THRESHOLD = 50
#: Maximum messages retained per thread in short-term memory.
SHORT_TERM_MAX_MESSAGES = 100

# ====================== Two-tier Memory ======================
#: Maximum total line count for the two-tier memory summary.
MAX_TOTAL_LINES = 200
#: Maximum total byte size for the two-tier memory summary.
MAX_TOTAL_BYTES = 25 * 1024  # 25KB

# ====================== Tool operation result statuses ======================
#: Tool operation reported a successful outcome.
OP_STATUS_SUCCESS = "success"
#: Tool operation reported a failure.
OP_STATUS_ERROR = "error"

# ====================== Maintenance / Governance statuses ======================
#: Maintenance skipped because the memory count is below threshold.
MAINTENANCE_STATUS_SKIPPED = "skipped"
#: Maintenance governance cycle completed.
MAINTENANCE_STATUS_COMPLETED = "completed"


# Memory tools tuple - gated by settings.ENABLE_MEMORY
# Imported here to avoid circular imports; actual tools defined in tools.py
_MEMORY_TOOLS: tuple = ()


# Will be populated by tools.py after tool definitions
def register_memory_tools(*tools):
    """Called by tools.py to register the memory tool functions."""
    global _MEMORY_TOOLS
    _MEMORY_TOOLS = tools


def get_memory_tools():
    """Get the registered memory tools."""
    return _MEMORY_TOOLS
