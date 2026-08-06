"""Environment formatting utilities for agent-facing display.

Methods in this module format environment-level data (app rankings, device
usage, etc.) without depending on domain or engine internals.
"""

from app.utils.template import render_template


def format_app_rankings(records: list, platform: str) -> str:
    """Format app usage rankings for display.

    Args:
        records: Iterable of objects with ``app_name``, ``bundle_id``,
            ``priority_score`` and optionally ``is_running`` attributes.
        platform: Platform label to display (e.g., "Android", "macOS").

    Returns:
        Rendered string using the common/events/system_tools.prompt.j2 template.
    """
    cp_data = []
    for r in records:
        status = " [RUNNING]" if getattr(r, "is_running", False) else ""
        cp_data.append({
            "id": 0,
            "name": f"{getattr(r, 'app_name', 'Unknown')} ({getattr(r, 'bundle_id', 'N/A')})",
            "status": f"Score {getattr(r, 'priority_score', 0):.2f}{status}",
            "time": platform,
        })
    return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)
