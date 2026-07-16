"""
Shared AppKit/HIServices helpers for the macOS driver.

Hard-won platform facts (see ATLAS_CHAIN_VERIFICATION.md §四十一):
- NSWorkspace.runningApplications()/frontmostApplication() are notification-fed
  snapshots; a long-lived process without a spinning NSRunLoop (e.g. uvicorn)
  NEVER sees updates. Always refresh via the runloop before reading.
- AXPosition/AXSize are AXValueRef wrappers, not CGPoint/structs — attribute
  access (.x / .width) fails silently; must AXValueGetValue-unpack.
- Process liveness for a bundle id is best checked with pgrep -f on the
  executable path (NSBundle), not via NSWorkspace snapshots.
"""

import logging
import subprocess
from typing import Any, cast

logger = logging.getLogger(__name__)


def _appkit() -> Any:
    import AppKit

    return AppKit


def _hiservices() -> Any:
    try:
        import HIServices

        return HIServices
    except ImportError:
        import Quartz

        return Quartz


def refresh_workspace_snapshot(spin_seconds: float = 0.05) -> None:
    """Spin the runloop briefly so NSWorkspace notification-fed snapshots
    (frontmostApplication/runningApplications) are up to date."""
    try:
        AppKit = _appkit()
        AppKit.NSRunLoop.currentRunLoop().runUntilDate_(
            AppKit.NSDate.dateWithTimeIntervalSinceNow_(spin_seconds)
        )
    except (ValueError, OSError, RuntimeError, TypeError) as e:
        logger.debug(f"runloop spin failed: {e}")


def frontmost_application() -> Any | None:
    """frontmostApplication() with a guaranteed-fresh snapshot."""
    refresh_workspace_snapshot()
    try:
        AppKit = _appkit()
        NSWorkspace = cast(Any, getattr(AppKit, "NSWorkspace", None))
        if NSWorkspace is None:
            return None
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except (ValueError, OSError, RuntimeError, TypeError) as e:
        logger.debug(f"frontmost_application failed: {e}")
        return None


def ax_value_point(ref: Any) -> tuple[int, int] | None:
    """Unpack an AXValueRef-wrapped CGPoint. Returns (x, y) or None."""
    if ref is None:
        return None
    HS = _hiservices()
    try:
        ok, pt = HS.AXValueGetValue(ref, HS.kAXValueCGPointType, None)
        if ok:
            return int(pt.x), int(pt.y)
    except (ValueError, TypeError):
        pass
    return None


def ax_value_size(ref: Any) -> tuple[int, int] | None:
    """Unpack an AXValueRef-wrapped CGSize. Returns (w, h) or None."""
    if ref is None:
        return None
    HS = _hiservices()
    try:
        ok, sz = HS.AXValueGetValue(ref, HS.kAXValueCGSizeType, None)
        if ok:
            return int(sz.width), int(sz.height)
    except (ValueError, TypeError):
        pass
    return None


def ax_copy_attribute(element: Any, attribute: str) -> Any | None:
    """AXUIElementCopyAttributeValue returning the value or None."""
    HS = _hiservices()
    try:
        err, val = HS.AXUIElementCopyAttributeValue(element, attribute, None)
        if err == 0:
            return val
    except (ValueError, TypeError):
        pass
    return None


def executable_path_for_bundle(bundle_id: str) -> str | None:
    """Executable path of an installed app bundle (for pgrep/pkill -f)."""
    try:
        AppKit = _appkit()
        url = AppKit.NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(bundle_id)
        if url is None:
            return None
        bundle = AppKit.NSBundle.bundleWithURL_(url)
        exe = bundle.executableURL() if bundle is not None else None
        return exe.path() if exe is not None else None
    except (ValueError, OSError, RuntimeError, TypeError) as e:
        logger.debug(f"executable_path_for_bundle({bundle_id}) failed: {e}")
        return None


def running_pid_for_bundle(bundle_id: str) -> int | None:
    """Snapshot-free liveness check: pgrep -f on the executable path."""
    exe = executable_path_for_bundle(bundle_id)
    if not exe:
        return None
    try:
        r = subprocess.run(["pgrep", "-f", exe], capture_output=True, timeout=10)
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(f"pgrep failed for {bundle_id}: {e}")
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.decode().split()
    return int(out[0]) if out else None


def ensure_app_running(bundle_id: str, wait_windows: float = 20.0) -> int | None:
    """Launch via `open -b` (retried — LaunchServices throttles relaunch right
    after a kill) and poll until windows materialize. Focus NOT required, but
    note a cold-launched app may steal focus once (§四十二)."""
    import time

    next_open = 0.0
    deadline = time.time() + wait_windows
    while time.time() < deadline:
        pid = running_pid_for_bundle(bundle_id)
        if pid is None:
            if time.time() >= next_open:
                try:
                    subprocess.run(["open", "-b", bundle_id], capture_output=True, timeout=15)
                except (subprocess.TimeoutExpired, OSError) as e:
                    logger.debug(f"open -b {bundle_id} failed: {e}")
                next_open = time.time() + 4.0
            time.sleep(0.3)
            continue
        try:
            HS = _hiservices()
            app_el = HS.AXUIElementCreateApplication(pid)
            if ax_copy_attribute(app_el, "AXWindows"):
                time.sleep(0.5)
                return pid
        except (ValueError, TypeError) as e:
            logger.debug(f"window probe failed for {bundle_id}: {e}")
        time.sleep(0.6)
    return running_pid_for_bundle(bundle_id)
