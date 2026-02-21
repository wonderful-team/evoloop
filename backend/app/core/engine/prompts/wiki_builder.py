from typing import List
from app.infrastructure.config.service import SystemConfigService
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
        relevant_files = i18n.get("prompts.wiki.generated_content.relevant_files")
        files_used = i18n.get("prompts.wiki.generated_content.files_used")
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
<summary>{relevant_files}</summary>

{files_used}

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

    @staticmethod
    def build_concept_extraction_prompt(page_title: str, page_content: str) -> str:
        """
        Prompt to extract key knowledge concepts from a generated Wiki page.
        These concepts will be stored in Agent memory for future reference.
        """
        # Truncate content to avoid context overflow
        truncated_content = page_content[:6000] if len(page_content) > 6000 else page_content
        
        return f"""You are a Knowledge Engineer analyzing a Wiki page to extract key concepts worth remembering.

Page Title: "{page_title}"

Page Content:
<wiki_content>
{truncated_content}
</wiki_content>

{WikiBuilder._get_lang_instruction()}

### Extraction Criteria
Extract concepts that are:
1. **Project-Specific Decisions**: e.g., "Uses Neo4j for knowledge graph storage"
2. **Development Patterns**: e.g., "Service layer uses async/await pattern"
3. **Configuration Details**: e.g., "Vector dimensions configured in settings.EMBEDDING_DIMENSIONS"
4. **Architecture Patterns**: e.g., "Two-phase Wiki generation workflow"
5. **Key Business Logic**: e.g., "Order status transitions through 5 states"

Do NOT extract:
- Generic programming terms (function, class, variable)
- Standard library usage
- Obvious implementation details

### Output Format
Return a JSON object:
{{
  "concepts": [
    {{
      "name": "Concept Name (usually English/technical term)",
      "description": "Concise description in target language explaining what it is and why it matters"
    }}
  ]
}}

Extract at most 5 concepts. Return empty list if nothing noteworthy.
"""

    @staticmethod
    def build_validation_prompt(structure: dict, project_context: str = "") -> str:
        """
        Prompt to validate Wiki structure completeness.
        Uses LLM to dynamically identify what should be covered based on project type,
        NOT a hardcoded checklist.
        """
        import json
        structure_json = json.dumps(structure, ensure_ascii=False, indent=2)
        
        return f"""You are a Documentation Completeness Analyst.

Your task is to analyze a proposed Wiki structure and identify any significant gaps.

### Project Context
{project_context if project_context else "Analyze the structure to infer project type."}

### Proposed Wiki Structure
<wiki_structure>
{structure_json}
</wiki_structure>

{WikiBuilder._get_lang_instruction()}

### Analysis Instructions
1. First, INFER the project type from the structure (e.g., software project, business process documentation, research notes, hardware manual, etc.)
2. Based on the project type, identify what key areas SHOULD typically be documented
3. Compare against the proposed structure
4. List any significant gaps

### Output Format
Return a JSON object:
{{
  "project_type": "Inferred type (e.g., 'Python Backend Service', 'E-commerce System', 'Hardware Manual')",
  "expected_coverage": ["Area 1", "Area 2", "..."],
  "gaps": [
    {{
      "area": "Missing area name",
      "reason": "Why this should be included",
      "suggested_title": "Suggested page title"
    }}
  ],
  "is_complete": true/false
}}

If the structure is reasonably complete for its project type, return is_complete=true with empty gaps.
Be practical - not every project needs exhaustive documentation.
"""
