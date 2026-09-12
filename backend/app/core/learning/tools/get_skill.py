import json
import logging

from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.get_skill")
async def get_skill(
    skill_id: int | None = None,
    skill_name: str | None = None,
) -> str:
    """
    Read the full definition of a specific skill (description, SOP, required tools).

    Args:
        skill_id: The exact numerical ID of the skill (obtained from list_skills).
        skill_name: The name of the skill (alternative to skill_id).
    """
    from app.core.learning.skills.discovery import skill_discovery

    if skill_id is not None:
        match, relevant, _ = await skill_discovery.exact_search(str(skill_id))
    elif skill_name:
        match, relevant, _ = await skill_discovery.exact_search(skill_name)
    else:
        return "get_skill requires skill_id or skill_name. Use list_skills to discover available skills."

    if match and relevant:
        skill_obj = relevant[0]
        tools_req = []
        # v3.1：优先从 capability.tools 展开（包声明是运行时权威），
        # fallback 旧 tools_used（学习管线记录）
        cap = getattr(skill_obj, "capability", None)
        if cap and isinstance(cap.get("tools"), list):
            for entry in cap["tools"]:
                server = entry.get("mcp_server") or ""
                include = entry.get("include") or []
                if include:
                    tools_req.extend(f"{server}:{t}" for t in include)
                else:
                    tools_req.append(server)
        elif skill_obj.tools_used:
            try:
                tools_req = json.loads(skill_obj.tools_used)
            except Exception as e:
                logger.exception(f"[get_skill] Malformed tools_used JSON: {e}")
                tools_req = []

        content = f"### Found Skill: {match.skill_name}\n\n"
        content += f"**Description**: {skill_obj.description}\n\n"
        if skill_obj.resource_path:
            content += f"**Skill Resource Path**: `{skill_obj.resource_path}`\n"
            content += "All relative paths in this SOP are relative to the project root (the parent directory of `skills/`).\n\n"
        content += (
            f"#### SOP (Standard Operating Procedure):\n{skill_obj.instructions}\n\n"
        )
        if tools_req:
            content += f"**Required Tools**: {', '.join(tools_req)}\n\n"

        content += "*Instruction: Strictly follow these instructions to complete the task. Ensure you have the required tools authorized.*"

        return content, {
            "count": 1,
            "result_type": "match",
            "skill_name": match.skill_name,
            "skill_id": match.skill_id,
            "tools_required": tools_req,
        }

    return (
        f"No skill found for ID/name: {skill_id or skill_name}. Try running list_skills to find the correct one.",
        {"count": 0, "result_type": "no_match"},
    )
