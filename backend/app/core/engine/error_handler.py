import logging
from typing import Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorClassification(BaseModel):
    """Structured error classification result."""
    error_type: str
    status_code: Optional[int] = None
    title: str
    message: str
    hint: str
    raw_error: str
    is_terminal: bool = False


class LLMErrorHandler:
    """Centralized handler for LLM and Platform related exceptions."""

    @staticmethod
    def classify_exception(e: Exception) -> ErrorClassification:
        """
        Classifies an exception into a standard EvoLoop error type.
        
        Returns:
            ErrorClassification object with type, localized messages, and hints.
        """
        from app.i18n.service import i18n
        import openai

        error_str = str(e).lower()
        error_full = str(e)
        exc_name = type(e).__name__.lower()
        
        error_type = "llm_invocation_system"
        status_code = None
        is_terminal = False

        # 1. Detection Logic
        
        # [Platform Auth] EvoLoop platform auth errors
        if "not authenticated with evoloop" in error_str or "please login first" in error_str:
            error_type = "auth_expired"
            status_code = 401
            is_terminal = True
        
        # [LLM Auth] API Key issues
        elif isinstance(e, openai.AuthenticationError) or (
            "unauthorized" in error_str and ("401" in error_full or "auth" in error_str)
        ):
            error_type = "llm_auth"
            status_code = 401
            is_terminal = True
            
        # [Quota] Quota exhausted
        elif any(kw in error_str for kw in ("quota", "insufficient quota", "usage limit", "billing cycle", "credit", "balance", "insufficient_quota")):
            error_type = "quota_exhausted"
            status_code = 403
            is_terminal = True
            
        # [Rate Limit] Rate limiting
        elif "rate limit" in error_str or "too many requests" in error_str or "429" in error_full:
            error_type = "rate_limit"
            status_code = 429
            
        # [Service] Provider downtime
        elif any(kw in error_str for kw in ("unavailable", "overloaded", "gateway", "service error", "503", "502", "504")):
            error_type = "service_unavailable"
            status_code = 503
            
        # [Network] Connection issues
        elif any(kw in error_str for kw in ("timeout", "connection", "socket", "network", "httpx")):
            error_type = "network_error"
            
        # [Model] Model not found
        elif "model_not_found" in error_str or "not found" in error_str:
            error_type = "model_not_found"
            status_code = 404
            is_terminal = True

        # [Config] General invalid config
        elif "invalid_config" in error_str or "configuration" in error_str:
            error_type = "invalid_config"
            is_terminal = True

        # 2. Localized Content Retrieval
        # Use a unified core_engine namespace for all agent-related infrastructure errors
        prefix = "core_engine"
        
        title = i18n.get(f"{prefix}.{error_type}_title") or i18n.get(f"{prefix}.system_error_title") or "Error"
        message = i18n.get(f"{prefix}.{error_type}_desc") or i18n.get(f"{prefix}.execution_failed") or str(e)
        hint = i18n.get(f"{prefix}.{error_type}_hint") or i18n.get(f"{prefix}.retry_prompt") or "Please try again later."
        
        # Special case for llm_auth to use solution key if available
        if error_type == "llm_auth":
            hint = i18n.get(f"{prefix}.llm_auth_error_solution") or hint

        return ErrorClassification(
            error_type=error_type,
            status_code=status_code,
            title=title,
            message=message,
            hint=hint,
            raw_error=error_full,
            is_terminal=is_terminal
        )
