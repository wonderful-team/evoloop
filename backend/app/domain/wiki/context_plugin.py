"""
Wiki context plugin: injects the project wiki page index into EvoContext
for prompt construction. Implements the core ContextPlugin Protocol.
"""

import logging

from sqlalchemy.exc import DBAPIError

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import EvoContext
from app.core.context.plugins import ContextPlugin, plugin_registry
from app.domain.wiki.service import wiki_service

logger = logging.getLogger(__name__)


class WikiContextPlugin(ContextPlugin):
    """
    Hydrates ``ctx.wiki_index`` with the project's wiki page index (title + summary).

    Returns an empty list in global mode (no project_id or DEFAULT_PROJECT_ID),
    and degrades to an empty list on database-level failures so prompt
    construction never crashes over advisory wiki context.
    """

    def hydrate(self, ctx: EvoContext) -> None:
        project_id = ctx.project_id
        if not project_id or project_id == DEFAULT_PROJECT_ID:
            ctx.wiki_index = []
            return
        try:
            ctx.wiki_index = wiki_service.get_wiki_index(project_id)
        except DBAPIError:
            logger.exception("[WikiContextPlugin] Failed to load wiki index for project %s", project_id)
            ctx.wiki_index = []


# Register the plugin globally
plugin_registry.register(WikiContextPlugin())
