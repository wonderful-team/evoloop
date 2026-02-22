from typing import Any

from pydantic import BaseModel, Field

from app.core.learning.discovery import SkillDiscovery
from app.core.tools import evoloop_tool


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
async def search_skills(query: str, namespace: str = None) -> dict[str, Any]:
    """
    Yellow Pages directory for finding Standard Operating Procedures (SOPs). Use this when you don't know how to perform a specific action before attempting to guess or write your own code.
    Looks up instructions for an action using a deterministic namespace and regex filter.
    Falls back to semantic/fuzzy lookup within the namespace if a regex match fails.
    Returns the markdown instructions if found.
    """
    discovery = SkillDiscovery()

    match, relevant = await discovery.exact_search(query=query, namespace_context=namespace)

    if match and relevant:
        is_fuzzy = match.confidence < 1.0
        instruction = "Execute this matching skill directly as a strict SOP." if not is_fuzzy else "A highly relevant SOP was found. Follow its strategy closely."

        skill_obj = relevant[0]

        return {
            "result_type": "fuzzy_match" if is_fuzzy else "exact_match",
            "instruction": instruction,
            "skill_name": match.skill_name,
            "skill_id": match.skill_id,
            "markdown_sop": skill_obj.instructions,
            "parameters": match.extracted_params,
            "confidence": match.confidence
        }

    if relevant:
        sops = [
            f"--- SOP: {s.name} ---\n{s.instructions}\n" for s in relevant if s.instructions
        ]
        if sops:
            return {
                "result_type": "namespace_context",
                "instruction": "Read these related SOPs and apply their strategies to your next actions.",
                "sops": "\n".join(sops)
            }

    return {
        "result_type": "no_match",
        "instruction": "No official SOP found for this domain. You must rely on your own reasoning to achieve the user's goal. Use autonomous verification tools frequently."
    }
