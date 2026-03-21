import os
import logging
from app.core.config import settings
from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry

logger = logging.getLogger(__name__)


class MemoryContextPlugin(ContextPlugin):
    """
    Injects episodic memory (journal.md) and core memory (focus.md) 
    into the EvoContext.
    """
    def hydrate(self, ctx: EvoContext) -> None:
        try:
            # 1. Load Episodic Memory (Journal)
            journal_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "knowledge", "journal.md")
            ctx.metadata["episodic_memory_raw"] = ""
            if os.path.exists(journal_path):
                with open(journal_path, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        # Keep last 20 lines as raw context for the template
                        ctx.metadata["episodic_memory_raw"] = "\n".join(content.splitlines()[-20:])

            # 2. Load Core Memory (Focus)
            focus_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "working", "focus.md")
            ctx.metadata["core_memory_raw"] = ""
            if os.path.exists(focus_path):
                with open(focus_path, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        ctx.metadata["core_memory_raw"] = content

        except Exception as e:
            logger.warning(f"Failed to hydrate MemoryContextPlugin: {e}")


# Register the plugin instance
plugin_registry.register(MemoryContextPlugin())
