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
