import logging

from app.core.tools import evoloop_tool
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=False,
    summary_template="evoloop.tool_summary.list_skills"
)
async def list_skills(namespace: str | None = None, query: str | None = None) -> str:
    """
    List available SOPs (Standard Operating Procedures) in the skill library.
    Use this to browse available skills to accomplish your task.

    Args:
        namespace: Optional ecosystem filter (e.g., 'android', 'macos', 'web').
        query: Optional search term to filter the list by keyword.
    """
    from app.core.learning.discovery import skill_discovery

    index = await skill_discovery.get_skills_catalog(namespace=namespace, query=query)
    count = len(index)
    ns = namespace or i18n.get("common.all", default="all")

    lines = [i18n.get("domain_tools.learning.list_skills.catalog_header", namespace=ns, count=str(count))]
    if not index:
        lines.append(i18n.get("domain_tools.learning.list_skills.no_skills"))
    else:
        for skill in index:
            lines.append(i18n.get("domain_tools.learning.list_skills.skill_item", id=skill['id'], name=skill['name'], description=skill['description']))

    lines.append(i18n.get("domain_tools.learning.list_skills.instruction"))

    return "\n".join(lines), {"count": count, "result_type": "index"}
