"""Context subsystem constants."""

# ====================== Context cache service ======================
#: Cache key prefix for persisted EvoContext data.
KEY_PREFIX = "evoloop:context"
#: Default TTL for persisted context data (seconds). 604800 = 7 days.
DEFAULT_TTL = 604800

# ====================== Layered context cache ======================
#: TTL for the static context layer (seconds). 300 = 5 minutes.
STATIC_TTL = 300
