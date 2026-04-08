"""
EvoCloud Endpoint Routing Configuration

Centralized routing logic for Split-Proxy architecture.
Determines whether an endpoint should be routed to Gateway or Member Center.
"""

from enum import Enum


class RouteTarget(Enum):
    """Routing target for API endpoints."""
    GATEWAY = "gateway"
    MEMBER_CENTER = "member"


# Endpoint prefixes routed to Gateway
# Order matters: more specific prefixes should come first
GATEWAY_PREFIXES: list[str] = [
    # WebSocket
    "/ws",
    "/health",
    
    # Gateway API v1
    "/api/v1/user",
    "/api/v1/quota",
    "/api/v1/auth/verify",
    "/api/v1/devices",
    
    # EvoLoop Link (Device Management) - Routed to Gateway
    "/evolooplink/api/device",
    "/evolooplink/api/command",
    "/evolooplink/api/log",
    "/evolooplink/api/llm",
]


def get_endpoint_route(endpoint: str) -> RouteTarget:
    """Determine routing target for an endpoint.
    
    Args:
        endpoint: API endpoint path (e.g., "/api/v1/user/profile")
        
    Returns:
        RouteTarget.GATEWAY or RouteTarget.MEMBER_CENTER
        
    Examples:
        >>> get_endpoint_route("/api/v1/user/profile")
        RouteTarget.GATEWAY
        
        >>> get_endpoint_route("/api/login/login")
        RouteTarget.MEMBER_CENTER
    """
    for prefix in GATEWAY_PREFIXES:
        if endpoint.startswith(prefix):
            return RouteTarget.GATEWAY
    return RouteTarget.MEMBER_CENTER


def is_gateway_endpoint(endpoint: str) -> bool:
    """Check if endpoint should be routed to Gateway.
    
    Args:
        endpoint: API endpoint path
        
    Returns:
        True if endpoint should be routed to Gateway
    """
    return get_endpoint_route(endpoint) == RouteTarget.GATEWAY


def get_routing_info() -> dict:
    """Get routing configuration information for debugging.
    
    Returns:
        Dictionary with routing configuration details
    """
    return {
        "gateway_prefixes": GATEWAY_PREFIXES,
        "gateway_prefix_count": len(GATEWAY_PREFIXES),
    }
