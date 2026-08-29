"""Identity and token storage constants."""

# ====================== Cache hash keys ======================
#: Cache hash key for token fields (cleared on logout).
TOKEN_HASH_KEY = "evoloop:tokens"
#: Cache hash key for the device identity field (survives logout).
DEVICE_IDENTITY_HASH_KEY = "evoloop:device:identity"

# ====================== Hash field names ======================
FIELD_ACCESS_TOKEN = "access_token"
FIELD_REFRESH_TOKEN = "refresh_token"
FIELD_MEMBER_ID = "member_id"
FIELD_DEVICE_KEY = "device_key"

# ====================== Token resolution cache ======================
#: Local/shared cache TTL for member_id / profile lookups from tokens (seconds).
TOKEN_CACHE_TTL = 120  # 2 minutes
