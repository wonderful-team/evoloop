"""Channel-agnostic Layer-0 routing constants.

String literals and tuning values that cross the router, classifier, and
cache modules are centralized here so typos and drift are easier to catch.
Enums such as :class:`app.core.routing.device_kind.DeviceKind` remain in
their dedicated enum modules.
"""

# ====================== Spec cache ======================
#: Shared cache key for the current enriched RouteCatalog.
SPEC_CACHE_KEY = "l0:init_spec:current"
#: Default debounce window for coalescing burst rebuild requests (seconds).
REBUILD_DEBOUNCE_SECONDS = 0.2

# ====================== Routing protocol intent/domain labels ======================
#: Functional intent for macro execution paths.
INTENT_MACRO_TASK = "macro_task"
#: Functional intent for delegated worker-agent paths.
INTENT_WORKER_TASK = "worker_task"
#: Functional intent for direct-answer / chitchat paths.
INTENT_DIRECT_ANSWER = "direct_answer"
#: Functional intent for memory-query paths.
INTENT_MEMORY_QUERY = "memory_query"
#: Functional intent for environment-query paths.
INTENT_ENVIRONMENT_QUERY = "environment_query"
#: Sentinel intent used when the L1 domain classifier provides the domain.
INTENT_DOMAIN_CLASSIFIED = "domain_classified"

#: Domain label returned when the classifier cannot disambiguate the request.
DOMAIN_AMBIGUOUS = "ambiguous"
#: Domain label returned when multiple distinct intents are detected.
DOMAIN_MULTI_INTENT = "multi_intent"

# ====================== ONNX domain classifier ======================
#: Confidence threshold below which the engine fallback mapping takes over.
CONFIDENCE_THRESHOLD = 0.6
