import json
from typing import Any

from pydantic import BaseModel, Field

from app.core.learning.discovery import SkillDiscovery
from app.core.tools import evoloop_tool


class SearchSkillsSchema(BaseModel):
    query: str = Field(
        "",
        description="The specific action or pattern you are looking to perform. e.g. 'click on save button'",
    )
    namespace: str = Field(
        None,
        description="Optional directory tree namespace to restrict the search. e.g. 'android', 'macos', 'browser'",
    )
    index_mode: bool = Field(
        False,
        description="If True, returns a high-level catalog of all skills in the namespace instead of searching for a specific match."
    )


@evoloop_tool(is_pollable=True)
async def search_skills(query: str = "", namespace: str = None, index_mode: bool = False) -> dict[str, Any]:
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
        return {
            "result_type": "index",
            "namespace": namespace or "all",
            "skills": index,
            "instruction": "Use these skill names/descriptions to decide your next step or perform a deeper search."
        }

    # 2. Search Mode: Find specific skills
    match, relevant, reasoning = await skill_discovery.exact_search(query=query, namespace_context=namespace)

    if match and relevant:
        skill_obj = relevant[0]
        tools_req = []
        if hasattr(skill_obj, "tools_used") and skill_obj.tools_used:
            try:
                tools_req = json.loads(skill_obj.tools_used)
            except Exception:
                pass

        return {
            "result_type": "match",
            "skill_name": match.skill_name,
            "skill_id": match.skill_id,
            "markdown_sop": skill_obj.instructions,
            "tools_required": tools_req,
            "confidence": match.confidence,
            "instruction": "If you route to a worker for this skill, ensure you authorize the 'tools_required' listed here."
        }

    if relevant:
        return {
            "result_type": "suggestions",
            "suggestions": [{"id": s.id, "name": s.name, "description": s.description} for s in relevant[:5]],
            "instruction": "No exact match, but these skills might be relevant. Search again with one of these names or use index_mode."
        }

    return {
        "result_type": "no_match",
        "instruction": f"No SOP found for '{query}'. **Divergence Tip**: Try searching for your semantic goal (e.g., 'collect market price') instead of tool names. If you cannot find a skill after 1-2 attempts, proceed with manual tool calls."
    }
