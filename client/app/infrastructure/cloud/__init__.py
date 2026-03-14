"""
Cloud client infrastructure for EvoLoop.

Provides client-side connectivity to EvoLoop Cloud services.
"""

from app.core.config import settings

# Conditional import - only load if cloud URL is configured
if settings.EVOLOOP_CLOUD_URL:
    from .client import CloudClient, CloudClientError, get_cloud_client
    from .protocol import CloudMessage, MessageType
else:
    # No-op implementations if cloud not configured
    from .client import CloudClientError
    from .noop import NoOpCloudClient as CloudClient, get_noop_client as get_cloud_client

__all__ = ["CloudClient", "CloudClientError", "get_cloud_client", "CloudMessage", "MessageType"]
