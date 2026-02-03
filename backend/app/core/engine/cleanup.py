
import logging
from typing import List

from sqlalchemy import delete

from app.core.memory import memory_manager
from app.infrastructure.database.sql.database import session_scope
from app.models.todo import TodoItem
from app.core.interfaces.cleanup import ICleanupHandler
from app.core.brain.cleanup import BrainCleanupHandler

logger = logging.getLogger(__name__)

class CleanupOrchestrator:
    """
    Central registry for cleanup handlers.
    Delegates cleanup of side effects to registered modules.
    """
    
    def __init__(self):
        self.handlers: List[ICleanupHandler] = []
        self._register_default_handlers()

    def _register_default_handlers(self):
        # 1. Brain Module Handler
        try:
            self.handlers.append(BrainCleanupHandler())
        except Exception as e:
            logger.error(f"Failed to register BrainCleanupHandler: {e}")

        # 2. Episode Handler (Memory Module) - implemented inline or via wrapper?
        # For simple interface calls, an inline wrapper or simple class is fine.
        class EpisodeCleanupHandler(ICleanupHandler):
            async def cleanup(self, message_ids: List[str]) -> int:
                try:
                    return await memory_manager.long_term.delete_episodes_by_message_ids(message_ids)
                except Exception as e:
                    logger.error(f"Episode cleanup failed: {e}")
                    return 0
        
        self.handlers.append(EpisodeCleanupHandler())

        # 3. Todo Handler (Domain/Engine Module)
        class TodoCleanupHandler(ICleanupHandler):
            async def cleanup(self, message_ids: List[str]) -> int:
                try:
                    async with session_scope() as session:
                        stmt = delete(TodoItem).where(TodoItem.source_message_id.in_(message_ids))
                        result = await session.execute(stmt)
                        return result.rowcount
                except Exception as e:
                    logger.error(f"Todo cleanup failed: {e}")
                    return 0

        self.handlers.append(TodoCleanupHandler())

    async def cleanup_all(self, message_ids: List[str]) -> dict:
        if not message_ids:
            return {}

        logger.info(f"CleanupOrchestrator: Rolling back side effects for {len(message_ids)} messages...")
        
        results = {}
        for handler in self.handlers:
            name = handler.__class__.__name__
            try:
                count = await handler.cleanup(message_ids)
                results[name] = count
                logger.info(f"Handler {name} cleaned {count} items.")
            except Exception as e:
                logger.error(f"Handler {name} failed: {e}")
                results[name] = -1

        return results

# Singleton instance
_orchestrator = CleanupOrchestrator()

async def cleanup_side_effects(message_ids: List[str]) -> dict:
    """
    Public entry point (keeps existing signature for compatibility).
    """
    return await _orchestrator.cleanup_all(message_ids)
