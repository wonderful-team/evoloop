"""Context subsystem constants."""

# ====================== Context cache service ======================
#: Cache key prefix for persisted EvoContext data.
KEY_PREFIX = "evoloop:context"

# ====================== Layered context cache ======================
#: TTL for the static context layer (seconds). 300 = 5 minutes.
STATIC_TTL = 300
