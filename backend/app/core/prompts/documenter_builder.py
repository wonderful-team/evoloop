from app.core.system import SystemConfigService
from app.i18n.service import i18n


class DocumenterPromptBuilder:
    @staticmethod
    def _get_lang_instruction() -> str:
        user_lang = SystemConfigService.get_language_preference()
        return f"""LANGUAGE PROTOCOL:
    User Preference: {user_lang}.
    All documentation topics and filenames (if appropriate) should respect this language.
    Specifically, the 'topic' description should be in {user_lang}.
    """

    @staticmethod
    def build_file_structure_prompt(tree_output: str, skills: list | None = None) -> str:
        skills_section = ""
        if skills:
            skills_section = "\n### 5. EXPERT GUIDANCE (SKILLS)\n"
            for s in skills:
                skills_section += f"#### 📘 Skill: {s.name}\n{s.instructions}\n"

        return f"""You are a Technical Documentation Architect.

Your goal is to design a Wiki structure for this project.
Based on the project structure, list the essential documentation pages we should create.
Strictly focus on internal technical documentation for developers.

Project Root:
{tree_output}

## Environment Awareness
{DocumenterPromptBuilder._build_env_summary()}

{skills_section}

Common Pages (create these if relevant):
- Overview/Introduction
- System Architecture
- API Reference
- Database Schema
- Component Interaction
- Configuration & Ops

Output a JSON object with a "pages" key:
{{
  "pages": [
    {{"filename": "overview.md", "topic": "Project Overview & Core Features"}},
    ...
  ]
}}

{DocumenterPromptBuilder._get_lang_instruction()}
"""

    @staticmethod
    def build_page_generation_prompt(topic: str, filename: str, skills: list | None = None) -> str:
        base_prompt = i18n.get(
            "prompts.documenter.page_generation",
            topic=topic,
            filename=filename
        )
        
        if not skills:
            return base_prompt

        blocks = ["\n### EXPERT GUIDANCE (SKILLS)",
                   "The following are expert guides relevant to this page topic.",
                   "Use these as your strategy reference when writing content.\n"]

        for skill in skills:
            block = f"#### 📘 Skill: {skill.name}\n"
            if skill.description:
                block += f"**Description**: {skill.description}\n"
            if skill.instructions:
                block += f"**Expert Guide (心法)**:\n{skill.instructions}\n"
            blocks.append(block)

        return base_prompt + "\n" + "\n".join(blocks)

    @staticmethod
    def _build_env_summary() -> str:
        try:
            from app.domain.environment.prompt_utils import build_environment_prompt
            # Documenter usually needs a balanced view
            return build_environment_prompt(relevance="auto")
        except:
            return ""
