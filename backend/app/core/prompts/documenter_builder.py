from app.i18n.service import i18n
from app.domain.system.service import SystemConfigService


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
    def build_file_structure_prompt(tree_output: str) -> str:
        return f"""You are a Technical Documentation Architect.

Your goal is to design a Wiki structure for this project.
Based on the project structure, list the essential documentation pages we should create.
Strictly focus on internal technical documentation for developers.

Project Root:
{tree_output}

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
    def build_page_generation_prompt(topic: str, filename: str) -> str:
        return i18n.get(
            "prompts.documenter.page_generation",
            topic=topic,
            filename=filename
        )
