"""
Jinja2-based prompts for requirement analysis and task breakdown.

Templates are loaded from the prompts/ directory.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template

# Get the directory containing this file
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Initialize Jinja2 environment
jinja_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _load_template(template_name: str) -> Template:
    """Load a Jinja2 template by name."""
    return jinja_env.get_template(template_name)


def render_analysis_prompt(
    document_content: str,
    focus_areas: list[str] | None = None,
    language: str = "Chinese"
) -> str:
    """
    Render the requirement analysis prompt.

    Args:
        document_content: The raw document content (markdown format)
        focus_areas: Optional list of focus areas
        language: Output language (default: Chinese)

    Returns:
        Rendered prompt string
    """
    template = _load_template("analysis_prompt.j2")
    return template.render(
        document_content=document_content,
        focus_areas=focus_areas,
        language=language
    )


def render_breakdown_prompt(
    title: str,
    summary: str,
    functional_requirements: list[dict],
    user_stories: list[dict],
    technical_suggestions: list[dict] | None = None,
    strategy: str = "module_based",
    language: str = "Chinese"
) -> str:
    """
    Render the task breakdown prompt.

    Args:
        title: Requirement title
        summary: Requirement summary
        functional_requirements: List of functional requirements
        user_stories: List of user stories
        technical_suggestions: Optional list of technical suggestions
        strategy: Breakdown strategy (module_based, layer_based, priority_based)
        language: Output language (default: Chinese)

    Returns:
        Rendered prompt string
    """
    template = _load_template("breakdown_prompt.j2")
    return template.render(
        title=title,
        summary=summary,
        functional_requirements=functional_requirements,
        user_stories=user_stories,
        technical_suggestions=technical_suggestions or [],
        strategy=strategy,
        language=language
    )


# For backward compatibility
REQUIREMENT_ANALYSIS_SYSTEM_PROMPT = """\
You are a senior product manager and system architect, specializing in extracting and structuring requirements from documents.

## Analysis Task
Please analyze the following requirement document and extract key information in a structured format.

## Input Document
```markdown
{document_content}
```

## Output Requirements
Please output in the following JSON structure:

```json
{{
  "title": "Requirement title (concise and clear)",
  "summary": "Requirement summary (within 200 words)",
  "functional_requirements": [
    {{
      "id": "FR-001",
      "description": "Functional requirement description",
      "priority": "high|medium|low",
      "category": "Category (e.g., User Management, Order System, Payment, etc.)",
      "acceptance_criteria": ["Criterion 1", "Criterion 2"]
    }}
  ],
  "non_functional_requirements": [
    {{
      "id": "NFR-001",
      "description": "Non-functional requirement description",
      "type": "performance|security|usability|reliability|scalability"
    }}
  ],
  "user_stories": [
    {{
      "id": "US-001",
      "role": "As a <user role>",
      "action": "I want to <functionality>",
      "benefit": "So that <value>",
      "acceptance_criteria": ["Given...When...Then...", "..."]
    }}
  ],
  "technical_suggestions": [
    {{
      "area": "Technical area",
      "suggestion": "Specific suggestion",
      "rationale": "Reasoning"
    }}
  ],
  "risks": [
    {{
      "description": "Risk description",
      "impact": "high|medium|low",
      "mitigation": "Mitigation strategy"
    }}
  ],
  "dependencies": ["Dependency 1", "Dependency 2"]
}}
```

## Rules
1. Functional requirements must be testable
2. User stories should follow INVEST principles
3. Prioritize based on business value and implementation complexity
4. Technical suggestions should be based on current technology trends
5. Focus Areas: {focus_areas}

Language: Please respond in {language}.
"""

TASK_BREAKDOWN_SYSTEM_PROMPT = """\
You are a senior project manager and technical lead, specializing in breaking down requirements into actionable development tasks.

## Breakdown Task
Based on the confirmed requirement analysis below, break down into specific development tasks.

## Input Requirements
Requirement Title: {title}
Requirement Summary: {summary}

Functional Requirements:
```json
{functional_requirements}
```

User Stories:
```json
{user_stories}
```

Technical Suggestions:
```json
{technical_suggestions}
```

## Output Requirements
Please output the task list in the following JSON structure:

```json
{{
  "tasks": [
    {{
      "title": "Task title (concise and clear, for task list display)",
      "description": "Detailed task description including:\\n- Objectives\\n- Implementation points\\n- Acceptance criteria",
      "requirement_refs": ["FR-001", "US-002"],
      "priority": "urgent|high|medium|low",
      "estimated_hours": 8,
      "category": "frontend|backend|database|devops|testing|design|other",
      "tags": ["Tag 1", "Tag 2"],
      "acceptance_criteria": ["Criterion 1", "Criterion 2"]
    }}
  ],
  "grouping_suggestion": "Suggested task grouping (e.g., by module, by iteration)"
}}
```

## Breakdown Rules
1. Task granularity should be controlled between 4-16 hours
2. Clearly define dependencies between tasks (use array index)
3. Consider possibilities for parallel development
4. Include necessary testing tasks
5. Consider frontend/backend/database division of labor
6. Mark tasks requiring technical research

Breakdown Strategy: {strategy}
Language: Please respond in {language}.
"""
