"""
Background agent error handling utilities.
"""

import json
import logging

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.classifier import MessageClassifier
from app.core.engine.message.event_bus import get_event_bus
from app.core.engine.message.sequence import SequenceService
from app.core.monitoring.activity import activity_monitor
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope
from app.models import Message
from app.models.schemas.events import QuotaExhaustedEvent

logger = logging.getLogger(__name__)


async def handle_task_exception(thread_id: str, project_id: int, e: Exception, handler=None):
    """Handle exceptions during graph execution using unified LLMErrorHandler.

    Args:
        handler: Optional MessageHandler instance for pushing errors to Mobile.
    """
    from app.core.exceptions import AgentHumanInterruptException
    from app.core.engine.error_handler import LLMErrorHandler

    # Check for human-interrupt or graph-interrupt using class checks
    # NOTE: langgraph.errors.GraphInterrupt may not be imported at module level
    # to avoid circular deps; we check by dotted name via getattr fallback.
    from langgraph.errors import GraphInterrupt as _GraphInterrupt
    if isinstance(e, (AgentHumanInterruptException, _GraphInterrupt)):
        logger.info(f"Task {thread_id} interrupted for human input: {e}")
        return

    logger.error(f"Error running thread {thread_id}: {e}", exc_info=True)

    # 1. Classify the exception
    classification = LLMErrorHandler.classify_exception(e)
    error_type = classification.error_type

    # 2. Handle specific terminal errors with dedicated UI flows
    # Helper to push critical errors to Mobile as well as SSE
    async def _push_to_mobile_if_handler(classification_obj):
        if handler:
            try:
                from app.core.engine.message.mobile_notifier import MobileErrorNotifier
                await MobileErrorNotifier(handler).push(classification_obj)
            except (TypeError, ValueError, RuntimeError, OSError) as push_e:
                logger.warning(f"[ErrorHandler] Mobile push failed: {push_e}")

    if error_type == "auth_expired":
        logger.warning(f"[EvoLoopAuth] Thread {thread_id} platform auth expired")
        await activity_monitor.end_run(thread_id, "failed")
        await get_event_bus().publish(
            f"chat:{thread_id}:events",
            json.dumps({
                "type": "auth_expired",
                "status": "auth_expired",
                "title": classification.title,
                "message": classification.message,
                "hint": classification.hint,
            })
        )
        await _push_to_mobile_if_handler(classification)
        return

    if error_type == "llm_auth":
        logger.warning(f"[LLMAuthError] Thread {thread_id} hit LLM API authentication error")
        await activity_monitor.end_run(thread_id, "failed")
        await get_event_bus().publish(
            f"chat:{thread_id}:events",
            json.dumps({
                "type": "llm_auth_error",
                "status": "failed",
                "title": classification.title,
                "message": classification.message,
                "hint": classification.hint,
            })
        )
        await _push_to_mobile_if_handler(classification)
        return

    if error_type == "quota_exhausted":
        logger.warning(f"[QuotaExhausted] Thread {thread_id} hit quota limit")
        await activity_monitor.end_run(thread_id, "quota_exhausted")
        await get_event_bus().publish(
            f"chat:{thread_id}:events",
            QuotaExhaustedEvent(
                type="quota_exhausted",
                title=classification.title,
                message=classification.message,
                hint=classification.hint,
                action_text=i18n.get('core_engine.quota_exhausted_action'),
            ).model_dump_json()
        )
        await _push_to_mobile_if_handler(classification)
        return

    # 3. Handle Retryable or Fatal errors
    await activity_monitor.end_run(thread_id, "failed")

    # Standard classification of "retryable" keywords
    is_retryable = error_type in ("rate_limit", "service_unavailable", "network_error")

    icon_warning = i18n.get('icons.warning') or '⚠️'
    icon_failed = i18n.get('icons.failed') or '❌'

    raw_error_snippet = (classification.raw_error or "")[:200]
    if is_retryable:
        user_message = (
            f"{icon_warning} **{classification.title}**: "
            f"{classification.message}\n\n"
            f"{classification.hint}\n\n"
            f"> {raw_error_snippet}"
        )
        action_type = "warning"
    else:
        # Generic system/config error
        user_message = (
            f"{icon_failed} **{classification.title}**: "
            f"{classification.message}\n\n"
            f"{classification.hint}\n\n"
            f"> {raw_error_snippet}"
        )
        action_type = "system"

    # Persist the failure message to DB for visibility and future learning (if applicable)
    await persist_system_error(thread_id, project_id, user_message, action_type=action_type, run_id=handler.run_id if handler else None)

    # 4. Push error to Mobile (统一走 MobileErrorNotifier)
    if handler:
        from app.core.engine.message.mobile_notifier import MobileErrorNotifier
        await MobileErrorNotifier(handler).push(classification)


async def persist_system_error(
    thread_id: str,
    project_id: int,
    error_details: str,
    action_type: str = "system",
    run_id: str | None = None,
):
    """Save a system error message to the database.

    If the error is classified as ERROR_SYSTEM or AUTH_EXPIRED,
    it is NOT persisted (per MessageCategory design). These errors are
    infrastructure-level and provide no value for agent learning.
    """
    # Classify the error content
    category = MessageClassifier.classify_ai_message(
        content=error_details,
        metadata={"is_error": True, "error_type": action_type}
    )

    # Skip persistence for system-level errors
    if category in (MessageCategory.ERROR_SYSTEM, MessageCategory.AUTH_EXPIRED):
        logger.debug(f"[_persist_system_error] Skipping persistence for {category} error")
        return

    try:
        import uuid
        async with session_scope() as session:
            # Get next sequence (atomic)
            seq = await SequenceService.next_sequence(thread_id)

            error_msg = Message(
                id=str(uuid.uuid4()),
                thread_id=thread_id,
                project_id=project_id,
                role="ai",
                action_type=action_type,
                content=error_details,
                sequence_number=seq,
                category=category.value,
                status="failed",
                content_type="markdown",
                is_visible=False,
                run_id=run_id,
            )
            session.add(error_msg)
    except (TypeError, ValueError, RuntimeError, OSError) as db_e:
        logger.error(
            f"Failed to persist error message for thread {thread_id}: {type(db_e).__name__}: {db_e}",
            exc_info=True,
        )
