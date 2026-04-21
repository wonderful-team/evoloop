"""
LLM error classification utilities.

Converts raw LLM exceptions into typed InferenceError objects with
user-friendly messages.
"""

import logging

logger = logging.getLogger(__name__)


class InferenceError(Exception):
    """Raised when LLM inference fails with a classified error."""

    def __init__(self, error_type: str, status_code: int | None, user_friendly_msg: str, raw_error: str):
        self.error_type = error_type
        self.status_code = status_code
        self.user_friendly_msg = user_friendly_msg
        self.raw_error = raw_error
        super().__init__(raw_error)


def classify_llm_error(e: Exception) -> InferenceError:
    """Classify LLM exception into InferenceError."""
    import openai

    error_str = str(e).lower()
    error_type = "llm_invocation_system"
    status_code = None

    if "not authenticated with evoloop" in error_str or "please login first" in error_str:
        error_type = "auth_expired"
        status_code = 401
    elif isinstance(e, openai.OpenAIError):
        if hasattr(e, "status_code"):
            status_code = e.status_code

    if error_type != "auth_expired":
        if status_code == 401 or "unauthorized" in error_str or "auth" in error_str:
            error_type = "llm_auth"
            status_code = 401
        elif status_code == 403:
            if "quota" in error_str or "usage limit" in error_str or "billing" in error_str:
                error_type = "quota_exhausted"
            else:
                error_type = "llm_auth"
        elif status_code == 429 or "rate limit" in error_str or "too many requests" in error_str:
            error_type = "rate_limit"
            status_code = 429

    if status_code in (500, 502, 503, 504) or any(kw in error_str for kw in ("unavailable", "overloaded", "gateway", "service error")):
        error_type = "service_unavailable"
        status_code = status_code or 503
    elif any(kw in error_str for kw in ("timeout", "connection", "socket", "network")):
        error_type = "network_error"
    elif "model_not_found" in error_str or "not found" in error_str:
        error_type = "invalid_config"
        status_code = 404

    user_friendly = get_user_friendly_error(error_type, str(e))
    return InferenceError(error_type, status_code, user_friendly, str(e))


def get_user_friendly_error(error_type: str, raw_error: str) -> str:
    """Convert technical errors to user-friendly messages."""
    from app.i18n.service import i18n

    error_messages = {
        "llm_auth": i18n.get("errors.llm_auth", default="Authentication failed. Please check your API key configuration."),
        "auth_expired": i18n.get("errors.auth_expired", default="EvoLoop session expired. Please login again to continue."),
        "quota_exhausted": i18n.get("errors.quota_exhausted", default="API quota exhausted. Please try again later or contact support."),
        "rate_limit": i18n.get("errors.rate_limit", default="Request rate limit reached. Please wait a moment and try again."),
        "service_unavailable": i18n.get("errors.service_unavailable", default="AI service is temporarily unavailable. Please try again in a moment."),
        "network_error": i18n.get("errors.network_error", default="Network connection issue. Please check your internet connection."),
        "invalid_config": i18n.get("errors.invalid_config", default="Invalid AI model configuration. Please check your settings."),
    }
    return error_messages.get(error_type, i18n.get("errors.llm_generic", default="An error occurred while processing your request. Please try again."))
