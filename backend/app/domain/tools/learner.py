import os
import subprocess

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.core.llm.factory import LLMFactory
from app.domain.memory.service import memory_service
from app.i18n.service import i18n
from app.logging import get_context, logger


class Concept(BaseModel):
    name: str = Field(description="Name of the concept, technology, or pattern")
    description: str = Field(description="Concise description of what it is and how it is used in this project")
    related_files: list[str] = Field(description="List of file paths related to this concept", default_factory=list)


class ExtractionResult(BaseModel):
    concepts: list[Concept] = Field(description="List of extracted concepts")


HARVEST_PROMPT = """You are a Knowledge Engineer.
Analyze the following code changes (git diff) and extract new "Domain Concepts", "Architecture Patterns", or "Important Decisions".

Criteria for a Concept:
- It is a specific term, class, module, or pattern used in the code.
- It is NOT a generic programming term (like "function", "array") unless used in a specific way.
- It is worth remembering for future tasks (e.g. "PaymentGateway" logic, "RetryPolicy" configuration).

Diff:
{diff}

Extract up to 5 most important concepts.
Output a JSON object.
"""


@tool
async def harvest_knowledge():
    """
    Analyze uncommitted changes (working directory) to extract and save new Knowledge Concepts.
    Call this at the end of a task to 'learn' from the work done.

    Works with both staged and unstaged changes in the working directory.
    """
    ctx = get_context()
    project_id = ctx.get("project_id", 1)
    cwd = ctx.get("working_directory") or os.getcwd()

    # 0. Check if Git repo exists
    git_dir = os.path.join(cwd, ".git")
    if not os.path.exists(git_dir):
        return i18n.get("prompts.domain_tools.learner.no_git")

    # 1. Get Git Diff (working directory vs HEAD)
    try:
        # Compare working directory against HEAD (captures uncommitted changes)
        cmd = ["git", "diff", "HEAD"]
        process = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
        diff_text = process.stdout

        if not diff_text.strip():
            return i18n.get("prompts.domain_tools.learner.no_changes")

        # Limit diff size to avoid context overflow
        if len(diff_text) > 10000:
            diff_text = diff_text[:10000] + "\n...(truncated)"

    except subprocess.TimeoutExpired:
        return i18n.get("prompts.domain_tools.learner.git_timeout")
    except Exception as e:
        return i18n.get("prompts.domain_tools.learner.git_error", error=str(e))

    # 2. Extract Concepts using LLM
    llm = LLMFactory.create_llm()
    structured_llm = llm.with_structured_output(ExtractionResult)

    from app.domain.system.service import SystemConfigService

    user_lang = SystemConfigService.get_language_preference()

    lang_directive = f"\n\nLANGUAGE PROTOCOL:\nUser Language: {user_lang}\nConcept 'description' fields MUST be written in {user_lang}.\nConcept 'name' should usually remain in English (Code)."

    try:
        result = await structured_llm.ainvoke([
            SystemMessage(content=HARVEST_PROMPT.format(diff=diff_text) + lang_directive)
        ], config={"callbacks": []})
    except Exception as e:
        logger.error(f"Harvest extraction failed: {e}")
        return i18n.get("prompts.domain_tools.learner.extract_error", error=str(e))

    # 3. Save to Memory
    saved_count = 0
    response_lines = [i18n.get("prompts.domain_tools.learner.harvested_header")]

    if result and result.concepts:
        for concept in result.concepts:
            # Add to Neo4j
            await memory_service.add_concept(
                name=concept.name,
                description=concept.description,
                project_id=project_id,
                related_files=concept.related_files,
            )
            saved_count += 1
            response_lines.append(f"- {concept.name}")

    if saved_count == 0:
        return i18n.get("prompts.domain_tools.learner.no_concepts")

    return "\n".join(response_lines)
