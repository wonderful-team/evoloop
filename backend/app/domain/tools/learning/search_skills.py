import json
import logging
from typing import Any

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=False,
    summary_template="evoloop.tool_summary.search_skills"
)
async def search_skills(query: str = "", namespace: str = None, index_mode: bool = False) -> str:
    """
    Search or browse the SOP (Standard Operating Procedure) library.
    Use this to find existing automation skills for specific domains (Android, MacOS, etc.).
    
    Args:
        query: Search term for specific actions.
        namespace: Ecosystem filter (e.g., 'android', 'macos', 'web').
        index_mode: Set to True to see the 'Table of Contents' for a namespace.
    """
    from app.core.learning.discovery import skill_discovery

    # 1. Index Mode: Browse the catalog
    if index_mode:
        index = await skill_discovery.get_namespace_index(namespace or "")
        count = len(index)

        lines = [f"### Skill Catalog: {namespace or 'all'} ({count} skills)"]
        if not index:
            lines.append("No skills found in this namespace.")
        else:
            for skill in index:
                lines.append(f"- **{skill['name']}**: {skill['description']}")
        
        lines.append("\n*Instruction: Use these skill names/descriptions to decide your next step or perform a deeper search.*")
        return "\n".join(lines), {"count": count, "result_type": "index"}

    # 2. Search Mode: Find specific skills
    match, relevant, reasoning = await skill_discovery.semantic_search(query=query, namespace_context=namespace)

    if match and relevant:
        skill_obj = relevant[0]
        tools_req = []
        if skill_obj.tools_used:
            try:
                tools_req = json.loads(skill_obj.tools_used)
            except Exception as e:
                logger.error(f"[search_skills] Malformed tools_used JSON: {e}")
                tools_req = []

        content = f"### Found Skill: {match.skill_name}\n\n"
        content += f"**Description**: {skill_obj.description}\n\n"
        content += f"#### SOP (Standard Operating Procedure):\n{skill_obj.instructions}\n\n"
        if tools_req:
            content += f"**Required Tools**: {', '.join(tools_req)}\n\n"
        
        content += f"*Instruction: If you route to a worker for this skill, ensure you authorize the 'tools_required' listed here.*"
        
        return content, {
            "count": 1, 
            "result_type": "match",
            "skill_name": match.skill_name,
            "skill_id": match.skill_id,
            "tools_required": tools_req
        }

    if relevant:
        suggestions = [{"id": s.id, "name": s.name, "description": s.description} for s in relevant[:5]]
        
        lines = [f"### No exact match for '{query}'"]
        lines.append("These skills might be relevant:")
        for s in suggestions:
            lines.append(f"- **{s['name']}**: {s['description']}")
            
        lines.append("\n*Instruction: Search again with one of these names or use index_mode.*")
        return "\n".join(lines), {"count": len(suggestions), "result_type": "suggestions"}

    return (
        f"No SOP found for '{query}'.\n\n"
        f"**Divergence Tip**: Try searching for your semantic goal (e.g., 'collect market price') instead of tool names. "
        f"If you cannot find a skill after 1-2 attempts, proceed with manual tool calls.",
        {"count": 0, "result_type": "no_match"}
    )
