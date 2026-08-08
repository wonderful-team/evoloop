"""
Environment utility helpers.

Consolidated utility functions for the environment domain:
- current-app context access (typed outlet over driver probes)
- app rankings display formatting
- host telemetry collection

Raw probing is delegated to the bottom layer (``app.infrastructure.drivers``);
this module only types / aggregates / formats.
"""

import logging

from app.core.environment.schemas.models import CurrentApp
from app.utils.template import render_template

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Current app
# ---------------------------------------------------------------------------
def get_current_app_context(device_id: str | None = None) -> CurrentApp:
    """Return the frontmost application as a typed :class:`CurrentApp`.

    Resolves from the ADB driver when ``device_id`` is given (Android),
    otherwise from the macOS driver.
    """
    if device_id:
        from app.infrastructure.drivers.adb import adb_driver

        info = adb_driver.get_current_app(device_id=device_id)
        if info.get("error"):
            return CurrentApp(platform="android")
        return CurrentApp(
            name=info.get("package", "unknown"),
            package=info.get("package"),
            activity=info.get("activity"),
            platform="android",
        )

    from app.infrastructure.drivers.macos import macos_driver

    info = macos_driver.get_current_app()
    if info.get("error"):
        return CurrentApp(platform="macos")
    return CurrentApp.model_validate({**info, "platform": "macos"})


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
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
            "name": (
                f"{getattr(r, 'app_name', 'Unknown')} "
                f"({getattr(r, 'bundle_id', 'N/A')})"
            ),
            "status": f"Score {getattr(r, 'priority_score', 0):.2f}{status}",
            "time": platform,
        })

    return render_template("common/events/system_tools.prompt.j2", checkpoints=cp_data)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------
def collect_cpu_mem() -> dict | None:
    """Collect CPU and memory metrics defensively.

    Returns a dict with ``cpu_percent``, ``load_avg``, ``mem_percent``,
    ``mem_available``, ``mem_used`` and ``mem_total``, or ``None`` if the
    snapshot could not be gathered.
    """
    from app.infrastructure.drivers.system import get_cpu_mem

    return get_cpu_mem()


def get_telemetry_dict() -> dict:
    """Get the awakened environment telemetry snapshot as a dict, or ``{}``.

    Consolidates the common ``get_awakened_state() -> get_telemetry_snapshot()
    -> model_dump()`` flow used by prompt builders and audit services.
    """
    from app.core.environment import get_awakened_state

    awakened_state = get_awakened_state()
    if not awakened_state:
        return {}
    try:
        snapshot = awakened_state.get_telemetry_snapshot()
        return snapshot.model_dump() if snapshot else {}
    except (AttributeError, ValueError, TypeError):
        logger.warning("Failed to build telemetry snapshot", exc_info=True)
        return {}
