import logging

from app.core.engine.schemas import ErrorClassification
from app.core.exceptions import InferenceError

logger = logging.getLogger(__name__)


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

        error_type = "llm_invocation_system"
        status_code = None
        is_terminal = False

        # 1. Detection Logic
        
        # [Circuit Breaker] Side-channel terminal error
        from app.core.exceptions import AgentTerminalException
        if isinstance(e, AgentTerminalException):
            error_type = e.error_type
            is_terminal = True
        
        # [Platform Auth] EvoLoop platform auth errors
        elif "not authenticated with evoloop" in error_str or "please login first" in error_str:
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

        # [Control] Recursion / Loop detection
        elif "recursion limit exceeded" in error_str or "stuck in a loop" in error_str:
            error_type = "recursion_limit"
            is_terminal = True

        # 2. Localized Content Retrieval
        # Use a unified core_engine namespace for all agent-related infrastructure errors
        prefix = "core_engine"
        
        title = i18n.get(f"{prefix}.{error_type}_title") or i18n.get(f"{prefix}.system_error_title") or "Error"
        message = i18n.get(f"{prefix}.{error_type}_desc", error=error_full) or i18n.get(f"{prefix}.execution_failed") or str(e)
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


    @staticmethod
    def raise_inference_error(e: Exception) -> None:
        """
        Classifies an exception and raises a standardized InferenceError.
        This provides a unified entry point for low-level LLM callers (e.g. InferenceEngine).
        """
        classification = LLMErrorHandler.classify_exception(e)
        
        # Combine message and hint for a better user experience
        user_msg = classification.message
        if classification.hint:
            user_msg = f"{user_msg}\n\n💡 {classification.hint}"

        raise InferenceError(
            error_type=classification.error_type,
            status_code=classification.status_code,
            user_friendly_msg=user_msg,
            raw_error=classification.raw_error
        )


import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

def with_llm_retry(max_attempts: int = 3, base_delay: float = 2.0, backoff: float = 2.0):
    """
    Standardized retry decorator for LLM API calls.
    Automatically classifies exceptions via LLMErrorHandler.
    Bypasses retries for terminal errors (auth, quota, context limit).
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    # Classify exception to see if it's terminal
                    classification = LLMErrorHandler.classify_exception(e)
                    
                    if classification.is_terminal or attempt == max_attempts:
                        logger.error(f"[LLMRetry] Terminal error or max attempts reached ({attempt}/{max_attempts}): {classification.error_type}")
                        raise
                        
                    logger.warning(
                        f"[LLMRetry] Attempt {attempt}/{max_attempts} failed: {classification.error_type}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff
            
            raise RuntimeError("Unexpected end of LLM retry loop")
        return wrapper
    return decorator
