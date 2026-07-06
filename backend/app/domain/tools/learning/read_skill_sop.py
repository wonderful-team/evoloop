import json
import logging

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(
    summary_template="evoloop.tool_summary.read_skill_sop"
)
async def read_skill_sop(skill_id: int) -> str:
    """
    Read the full Standard Operating Procedure (SOP) for a specific skill.
    
    Args:
        skill_id: The exact numerical ID of the skill (obtained from list_skills).
    """
    from app.core.learning.discovery import skill_discovery

    match, relevant, _ = await skill_discovery.exact_search(str(skill_id))
    
    if match and relevant:
        skill_obj = relevant[0]
        tools_req = []
        if skill_obj.tools_used:
            try:
                tools_req = json.loads(skill_obj.tools_used)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[read_skill_sop] Malformed tools_used JSON: {e}")
                tools_req = []

        content = f"### Found Skill: {match.skill_name}\n\n"
        content += f"**Description**: {skill_obj.description}\n\n"
        if skill_obj.resource_path:
            content += f"**Skill Resource Path**: `{skill_obj.resource_path}`\n"
            content += f"All relative paths in this SOP are relative to the project root (the parent directory of `skills/`).\n\n"
        content += f"#### SOP (Standard Operating Procedure):\n{skill_obj.instructions}\n\n"
        if tools_req:
            content += f"**Required Tools**: {', '.join(tools_req)}\n\n"
        
        content += f"*Instruction: Strictly follow these instructions to complete the task. Ensure you have the required tools authorized.*"
        
        return content, {
            "count": 1, 
            "result_type": "match",
            "skill_name": match.skill_name,
            "skill_id": match.skill_id,
            "tools_required": tools_req
        }
    
    return f"No SOP found with ID: {skill_id}. Try running list_skills to find the correct ID.", {"count": 0, "result_type": "no_match"}
