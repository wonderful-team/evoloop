import logging

from app.core.context import thread_context_store
from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry

logger = logging.getLogger(__name__)


class ProjectContextPlugin(ContextPlugin):
    """
    Plugin to automatically hydrate EvoContext with project-specific data.
    Links thread_id to working_directory and project_id via ThreadContextStore.
    """

    def hydrate(self, ctx: EvoContext) -> None:
        if not ctx.thread_id:
            # We can't do much without a thread_id hint
            return

        # 1. Sync Project ID
        if not ctx.project_id:
            pid = thread_context_store.get_active_project(ctx.thread_id)
            if pid:
                ctx.project_id = pid
                logger.debug(f"[ProjectPlugin] Hydrated project_id: {pid}")

        # 2. Sync Working Directory
        # Only hydrate from the legacy thread_context_store when the context has
        # no project-level working_directory yet. Do NOT overwrite a path that
        # has already been resolved from project_id by dispatch.
        existing_cwd = ctx.working_directory
        if existing_cwd and existing_cwd != thread_context_store.default_root:
            return

        managed_cwd = thread_context_store.get_working_directory(ctx.thread_id)
        if managed_cwd and managed_cwd != thread_context_store.default_root:
            ctx.working_directory = managed_cwd
            logger.debug(f"[ProjectPlugin] Hydrated working_directory: {managed_cwd}")


# Register the plugin globally
plugin_registry.register(ProjectContextPlugin())
