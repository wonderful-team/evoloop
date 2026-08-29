"""Wiki formatting utilities for agent-facing display.

Methods in this module turn domain wiki objects into prompt-ready strings
without leaking presentation details into the service layer.
"""

from app.utils.template import render_template


def format_wiki_pages(pages: list) -> str:
    """Format a list of wiki pages for display in a prompt.

    Args:
        pages: Iterable of objects with ``title`` and ``slug`` attributes.

    Returns:
        Rendered string using the core/vision/perceptions.prompt.j2 template.
    """
    if not pages:
        return render_template(
            "core/vision/perceptions.prompt.j2", type="wiki_pages", items=[]
        )
    items = [f"{p.title} (slug: {p.slug})" for p in pages]
    return render_template(
        "core/vision/perceptions.prompt.j2", type="wiki_pages", items=items
    )
