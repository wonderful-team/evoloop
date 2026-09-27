"""SDK conversation store lifecycle helpers (reset/resync boundaries).

The SDK EventLog persists per-thread under ``APP_DATA_DIR/sdk-conversations``.
When EvoLoop-side SSOT history is rolled back (rewind/retry) or the
conversation is deleted, the SDK store must be invalidated so the next
``run_turn`` replays the DB history into a fresh EventLog instead of
continuing on stale context.
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def conversation_store_path(thread_id: str) -> Path:
    """Mirror LocalConversation.get_persistence_dir for the derived id."""

    try:
        conversation_id = uuid.UUID(thread_id)
    except ValueError:
        conversation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"evoloop:{thread_id}")
    return Path(settings.APP_DATA_DIR) / "sdk-conversations" / conversation_id.hex


def reset_conversation_store(thread_id: str) -> bool:
    """Delete the persisted SDK conversation for a thread.

    Returns True when a store existed and was removed. Failure to clean up is
    logged but never raised: the next run_turn replays DB history only when the
    EventLog is empty, so a partially-removed store would still be detected via
    a subsequent divergence check — better to surface in logs than to break a
    user-facing rewind.
    """

    from app.core.engine.sdk_adapter import conversations

    cached = conversations.pop_cached(thread_id)
    if cached is not None:
        try:
            cached.conversation.close()
        except Exception:
            logger.exception(
                "[SDKBridge] closing evicted SDK conversation failed for %s",
                thread_id,
            )

    store = conversation_store_path(thread_id)
    if not store.exists():
        return False
    try:
        shutil.rmtree(store)
        logger.info("[SDKBridge] reset SDK conversation store for %s", thread_id)
        return True
    except OSError:
        logger.exception(
            "[SDKBridge] failed to reset SDK conversation store for %s", thread_id
        )
        return False
