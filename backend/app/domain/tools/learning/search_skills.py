from typing import Any, Dict
from pydantic import BaseModel, Field
from app.core.tools import evoloop_tool
from app.core.learning.discovery import SkillDiscovery

class SearchSkillsSchema(BaseModel):
    query: str = Field(
        ...,
        description="The specific action or pattern you are looking to perform. e.g. 'click on save button'",
    )
    namespace: str = Field(
        None,
        description="Optional directory tree namespace to restrict the search. e.g. 'os/macos' or 'browser/github'",
    )

@evoloop_tool
async def search_skills(query: str, namespace: str = None) -> Dict[str, Any]:
    """
    Yellow Pages directory for finding Standard Operating Procedures (SOPs). Use this when you don't know how to perform a specific action before attempting to guess or write your own code.
    Looks up instructions for an action using a deterministic namespace and regex filter.
    Returns the markdown instructions if found.
    """
    discovery = SkillDiscovery()
    
    match, relevant = await discovery.exact_search(query=query, namespace_context=namespace)
    
    if match and relevant:
        return {
            "result_type": "exact_match",
            "instruction": "Execute this matching skill directly.",
            "skill_name": match.skill_name,
            "skill_id": match.skill_id,
            "markdown_sop": relevant[0].instructions,
            "parameters": match.extracted_params
        }
        
    if relevant:
        sops = [
            f"--- SOP: {s.name} ---\n{s.instructions}\n" for s in relevant if s.instructions
        ]
        if sops:
            return {
                "result_type": "namespace_context",
                "instruction": "Read these related SOPs and apply their strategies to your next Bash command.",
                "sops": "\n".join(sops)
            }
            
    return {
        "result_type": "no_match",
        "instruction": "No official SOP found for this domain. You must rely on your own reasoning to write Bash commands to achieve the user's goal."
    }
