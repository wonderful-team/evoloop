"""
Embeddings Infrastructure Event Subscribers
============================================

Handles application-level lifecycle events for the embeddings module.

Includes:
- Preloading local embedding models on app start to avoid runtime HuggingFace downloads.
"""

import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)


@event_register()
class EmbeddingLifecycleSubscriber:
    """
    Handles initialization and warmup of embedding models at application startup.

    When a local embedder (e.g., SentenceTransformers) is configured, this
    subscriber triggers an eager model load so that the first user request does
    not block on a HuggingFace Hub download.
    """

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_application_started(self, event):
        """
        Handle APP_STARTED: Warm up the local embedding model if applicable.
        """
        try:
            from app.infrastructure.embeddings.factory import EmbedderFactory
            from app.infrastructure.embeddings.local import LocalEmbedder

            embedder = EmbedderFactory.get_embedder()
            if isinstance(embedder, LocalEmbedder):
                logger.info("[Embeddings] Preloading local embedding model...")
                await embedder._get_model()
                logger.info("[Embeddings] Local embedding model warmed up successfully.")
            else:
                logger.debug("[Embeddings] Non-local embedder configured, skipping warmup.")
        except Exception as exc:
            logger.warning(f"[Embeddings] Model warmup skipped (non-critical): {exc}", exc_info=True)
