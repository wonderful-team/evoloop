"""
EvoCloud Constants

Centralized constants for EvoCloud module configuration.

Note: For endpoint routing configuration, see routes.py
"""

# HTTP timeout settings (seconds)
DEFAULT_HTTP_TIMEOUT: int = 30

# WebSocket reconnect settings
WS_RECONNECT_BASE_DELAY: int = 5
WS_RECONNECT_MAX_DELAY: int = 60

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL: int = 30
