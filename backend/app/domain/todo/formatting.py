"""Todo formatting utilities for agent-facing display.

Methods in this module turn TodoItem collections into prompt-ready strings
without leaking presentation details into the todo service or tools.
"""

from app.utils.template import render_template


def format_todo_list(todos: list, title: str = None) -> str:
    """Format a todo list for display.

    Args:
        todos: Iterable of objects with ``status``, ``title``, ``id`` and
            ``due_date`` attributes.
        title: Optional heading for the list.

    Returns:
        The rendered prompt-ready string.
    """
    todo_data = []
    for t in todos:
        todo_data.append(
            {
                "status": t.status,
                "title": t.title,
                "id": t.id,
                "due_date": t.due_date,
            }
        )
    return render_template(
        "common/events/todo_list.prompt.j2", todos=todo_data, title=title
    )
