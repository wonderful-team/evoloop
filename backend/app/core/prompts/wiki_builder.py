
from typing import List
from app.core.config import settings
from app.domain.system.service import SystemConfigService
from app.constants import LANGUAGE_MAP
from app.i18n.service import i18n

class WikiBuilder:
    """
    Builder for Wiki Generation prompts, adapted from the 'Technical Writer' persona.
    """

    @staticmethod
    def _get_lang_instruction() -> str:
        # Get raw code (e.g. "zh") instead of human readable name from get_language_preference
        user_lang_code = SystemConfigService.get_value("LANGUAGE", "zh")
        target_lang = LANGUAGE_MAP.get(user_lang_code, "Mandarin Chinese (中文)")
        
        return f"""
IMPORTANT: The wiki content MUST be generated in {target_lang}.
"""

    @staticmethod
    def build_structure_prompt(file_tree: str, readme: str) -> str:
        """
        Prompt to determine the Wiki structure (list of pages) based on file tree.
        """
        return f"""You are an expert Technical Documentation Architect.
Your goal is to analyze a codebase and design a comprehensive Wiki structure.

1. The complete file tree of the project:
<file_tree>
{file_tree}
</file_tree>

2. The README file of the project:
<readme>
{readme}
</readme>

Determine the most logical structure for a wiki based on the repository's content.
{WikiBuilder._get_lang_instruction()}

CRITICAL: All "title" and "description" fields in the output JSON MUST be in the target language specified above.

Include pages that would benefit from visual diagrams, such as:
- Architecture overviews
- Data flow descriptions
- Component relationships
- Process workflows
- State machines
- Class hierarchies

Output a JSON object with the following structure:
{{
  "title": "Wiki Title",
  "description": "Brief description",
  "pages": [
    {{
      "id": "unique-slug-id",
      "title": "Page Title (Target Language)",
      "description": "What this page covers (Target Language)",
      "relevant_files": [
        "path/to/file1.py",
        "path/to/file2.ts"
      ],
      "importance": "high",
      "children": [
        {{
           "id": "subpage-id",
           "title": "Subpage Title",
           ...
        }}
      ]
    }},
    ...
  ]
}}
Use hierarchical structure (folders/groups) grouping related pages together where logical.
"""

    @staticmethod
    def build_content_prompt(page_title: str, relevant_files_content: str, relevant_file_paths: List[str]) -> str:
        """
        Prompt to generate the content of a single Wiki page.
        """
        files_list_md = "\n".join([f"- {path}" for path in relevant_file_paths])
        
        return f"""You are an expert technical writer and software architect.
Your task is to generate a comprehensive and accurate technical wiki page in Markdown format about a specific feature, system, or module.

Page Topic: "{page_title}"
{WikiBuilder._get_lang_instruction()}

You have access to the content of the following RELEVANT SOURCE FILES:
<relevant_files_content>
{relevant_files_content}
</relevant_files_content>

CRITICAL STARTING INSTRUCTION:
The very first thing on the page MUST be a `<details>` block listing ALL the source files you used.
Format it exactly like this:
<details>
<summary>{i18n.get("prompts.wiki.generated_content.relevant_files")}</summary>

{i18n.get("prompts.wiki.generated_content.files_used")}

{files_list_md}
</details>

Immediately after, the main title should be a H1 heading: `# {page_title}`.

GUIDELINES:
1. **Language:** The entire page content (headings, body text, explanations) MUST be in the target language. Code comments should be preserved or translated ensuring clarity.
2. **Introduction:** Concise purpose and scope.
3. **Detailed Sections:** Logic, components, flow. Use H2/H3.
4. **Mermaid Diagrams:** EXTENSIVELY use Mermaid (graph TD, sequenceDiagram, classDiagram). 
   - STRICTLY vertical orientation (graph TD).
   - Visualize architectures and flows found in the code.
5. **Tables:** Summarize API endpoints, config options, data models.
6. **Technical Accuracy:** Base everything SOLELY on the provided file content.
7. **Citations:** Cite specific files/lines where possible (e.g. `[source: file.py:10-20]`).

Do NOT include any preface or chatty intro. Start directly with the `<details>` block.
"""
