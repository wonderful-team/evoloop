"""System tools formatting utilities.

Formats checkpoint, autonomous task, signal and rollback outputs for the
common/events/system_tools.prompt.j2 template.
"""

from app.utils.template import render_template


class SystemToolsFormatter:
    """
    Utility class for formatting system tools outputs.

    Centralizes formatting for events/system_tools.prompt.j2 template
    used by checkpoint tools, scheduler, and system utilities.

    Usage:
        from app.core.execution.system_tools_formatter import SystemToolsFormatter

        # Format checkpoints
        return SystemToolsFormatter.checkpoints(checkpoint_list)

        # Format autonomous tasks
        return SystemToolsFormatter.autonomous_tasks(tasks)

        # Format signals
        return SystemToolsFormatter.signals(["Message 1", "Message 2"])
    """

    @staticmethod
    def checkpoints(checkpoints: list) -> str:
        """Format checkpoint list for display."""
        cp_data = []
        for cp in checkpoints:
            auto_tag = " [AUTO]" if getattr(cp, "created_by", None) == "auto" else ""
            status = "MANUAL" if getattr(cp, "created_by", None) == "manual" else "AUTO"
            cp_data.append(
                {
                    "id": getattr(cp, "id", 0),
                    "status": status,
                    "name": f"{getattr(cp, 'name', 'Unknown')}{auto_tag}",
                    "time": getattr(cp, "created_at", None)
                    and cp.created_at.strftime("%Y-%m-%d %H:%M")
                    or "",
                }
            )
        return render_template(
            "common/events/system_tools.prompt.j2", checkpoints=cp_data
        )

    @staticmethod
    def autonomous_tasks(tasks: list) -> str:
        """Format autonomous task list for display."""
        cp_data = []
        for t in tasks:
            status = (
                "DLQ" if t.is_dead_letter else ("Active" if t.is_active else "Paused")
            )
            cp_data.append(
                {
                    "id": t.id,
                    "status": status,
                    "name": t.intent_description[:50],
                    "time": f"Next: {t.next_run_at or 'Unknown'}",
                }
            )
        return render_template(
            "common/events/system_tools.prompt.j2", checkpoints=cp_data
        )

    @staticmethod
    def signals(messages: list[str]) -> str:
        """Format signal messages for display."""
        signal_data = [{"message": m} for m in messages]
        return render_template(
            "common/events/system_tools.prompt.j2", signals=signal_data
        )

    @staticmethod
    def rollback_preview(checkpoint_id: int, checkpoint_name: str) -> str:
        """Format rollback preview for display."""
        return render_template(
            "common/events/system_tools.prompt.j2",
            rollback_preview={"id": checkpoint_id, "name": checkpoint_name},
        )
