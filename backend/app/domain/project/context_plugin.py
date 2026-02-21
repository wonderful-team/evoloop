import logging
from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.domain.project.service import project_context_manager

logger = logging.getLogger(__name__)


class ProjectContextPlugin(ContextPlugin):
    """
    Plugin to automatically hydrate EvoContext with project-specific data.
    Links thread_id to working_directory and project_id via ProjectContextManager.
    """
    
    def hydrate(self, ctx: EvoContext) -> None:
        if not ctx.thread_id:
            # We can't do much without a thread_id hint
            return
            
        # 1. Sync Working Directory
        existing_cwd = ctx.working_directory
        managed_cwd = project_context_manager.get_working_directory(ctx.thread_id)
        
        if managed_cwd and managed_cwd != project_context_manager._default_root:
            if not existing_cwd:
                ctx.working_directory = managed_cwd
                logger.debug(f"[ProjectPlugin] Hydrated working_directory: {managed_cwd}")
        
        # 2. Sync Project ID
        if not ctx.project_id:
            pid = project_context_manager.get_active_project(ctx.thread_id)
            if pid:
                ctx.project_id = pid
                logger.debug(f"[ProjectPlugin] Hydrated project_id: {pid}")


# Register the plugin globally
plugin_registry.register(ProjectContextPlugin())
