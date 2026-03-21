"""
Jinja2-based prompts for requirement analysis and task breakdown.

Templates are loaded from the prompts/ directory.
"""

from app.utils import render_template


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
    return render_template(
        "requirements/analysis_prompt.j2",
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
    return render_template(
        "requirements/breakdown_prompt.j2",
        title=title,
        summary=summary,
        functional_requirements=functional_requirements,
        user_stories=user_stories,
        technical_suggestions=technical_suggestions or [],
        strategy=strategy,
        language=language
    )


# The f-strings have been removed in favor of Jinja2 templates.
# Use render_analysis_prompt and render_breakdown_prompt instead.
