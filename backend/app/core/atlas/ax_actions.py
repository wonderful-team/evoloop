"""
Runtime AX action primitives (M3) — focus-free, by-pid element actions.

These are the execution-side counterparts of the surveyor's read primitives:
locate by survey ax_path, press/activate, menu label-chain navigation, and
AXSetValue with mandatory read-back verification (M1.5 rule §四十二).

All functions are synchronous (HIServices is blocking) — call via
asyncio.to_thread from async code.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.core.atlas.constants import MAX_DEPTH
from app.infrastructure.drivers.macos.workspace import (
    ax_copy_attribute,
    ensure_app_running,
)

logger = logging.getLogger(__name__)


def _hs():
    import HIServices

    return HIServices


def locate(pid: int, path: str) -> Any | None:
    """Find the AXUIElement for a survey ax_path, or None."""
    HS = _hs()
    app_el = HS.AXUIElementCreateApplication(pid)
    roots: list[tuple[str, Any]] = []
    bar = ax_copy_attribute(app_el, "AXMenuBar")
    if bar is not None:
        roots.append(("menubar", bar))
    for i, w in enumerate(ax_copy_attribute(app_el, "AXWindows") or []):
        roots.append((f"window {i + 1}", w))

    def find(el: Any, current: str, target: str, depth: int) -> Any | None:
        if current == target:
            return el
        if depth > MAX_DEPTH:
            return None
        role = str(ax_copy_attribute(el, "AXRole") or "AXUnknown")
        for i, child in enumerate(ax_copy_attribute(el, "AXChildren") or []):
            hit = find(child, f"{current} > {role} {i + 1}", target, depth + 1)
            if hit is not None:
                return hit
        return None

    for prefix, root in roots:
        if path == prefix or path.startswith(prefix + " >"):
            return find(root, prefix, path, 0)
    return None


def press_at_path(pid: int, path: str, action: str = "AXPress") -> bool:
    el = locate(pid, path)
    if el is None:
        return False
    return _hs().AXUIElementPerformAction(el, action) == 0


def activate_at_path(pid: int, path: str) -> bool:
    """AXPress when advertised; else AXSelected=True (sidebar rows); else press
    the first descendant advertising AXPress."""
    HS = _hs()
    el = locate(pid, path)
    if el is None:
        return False
    err, action_names = HS.AXUIElementCopyActionNames(el, None)
    actions = [str(a) for a in action_names] if err == 0 and action_names else []
    if "AXPress" in actions:
        return HS.AXUIElementPerformAction(el, "AXPress") == 0
    err_s, settable = HS.AXUIElementIsAttributeSettable(el, "AXSelected", None)
    if err_s == 0 and settable:
        return HS.AXUIElementSetAttributeValue(el, "AXSelected", True) == 0
    for child in ax_copy_attribute(el, "AXChildren") or []:
        err2, child_actions = HS.AXUIElementCopyActionNames(child, None)
        names = [str(a) for a in child_actions] if err2 == 0 and child_actions else []
        if "AXPress" in names:
            return HS.AXUIElementPerformAction(child, "AXPress") == 0
    return False


def set_value_at_path(pid: int, path: str, text: str, verify: bool = True) -> bool:
    """AXSetValue with read-back verification (M1.5). Refuses non-settable or
    silently-rejecting targets (e.g. file-list name cells)."""
    el = locate(pid, path)
    if el is None:
        return False
    return _set_value_on_element(el, text, verify)


def find_by_role_label(pid: int, role: str, label: str) -> Any | None:
    """Resolve a window element by role+label at RUNTIME (structural ax_paths
    go stale as the UI evolves; labels like 地址和搜索栏 survive)."""
    HS = _hs()
    app_el = HS.AXUIElementCreateApplication(pid)
    for w in ax_copy_attribute(app_el, "AXWindows") or []:
        hit = _find_recursive(w, role, label, 0)
        if hit is not None:
            return hit
    return None


def _find_recursive(el: Any, role: str, label: str, depth: int) -> Any | None:
    if depth > MAX_DEPTH:
        return None
    if str(ax_copy_attribute(el, "AXRole") or "") == role:
        name = (
            ax_copy_attribute(el, "AXTitle")
            or ax_copy_attribute(el, "AXDescription")
            or ax_copy_attribute(el, "AXValue")
            or ""
        )
        if str(name).strip() == label:
            return el
    for child in ax_copy_attribute(el, "AXChildren") or []:
        hit = _find_recursive(child, role, label, depth + 1)
        if hit is not None:
            return hit
    return None


def perform_by_label(pid: int, role: str, label: str, action: str) -> bool:
    el = find_by_role_label(pid, role, label)
    if el is None:
        return False
    return _hs().AXUIElementPerformAction(el, action) == 0


def set_value_by_label(
    pid: int, role: str, label: str, text: str, verify: bool = True
) -> bool:
    el = find_by_role_label(pid, role, label)
    if el is None:
        return False
    return _set_value_on_element(el, text, verify)


def _set_value_on_element(el: Any, text: str, verify: bool) -> bool:
    HS = _hs()
    err, settable = HS.AXUIElementIsAttributeSettable(el, "AXValue", None)
    if err != 0 or not settable:
        return False
    if HS.AXUIElementSetAttributeValue(el, "AXValue", text) != 0:
        return False
    if not verify:
        return True
    time.sleep(0.2)
    readback = ax_copy_attribute(el, "AXValue")
    return isinstance(readback, str) and text in readback


def _menu_children(el: Any) -> list[Any]:
    """Direct menu children: for a bar item, descend into its AXMenu first."""
    kids = ax_copy_attribute(el, "AXChildren") or []
    out: list[Any] = []
    for k in kids:
        role = str(ax_copy_attribute(k, "AXRole") or "")
        if role == "AXMenu":
            out.extend(ax_copy_attribute(k, "AXChildren") or [])
        else:
            out.append(k)
    return out


def _menu_label(el: Any) -> str:
    name = (
        ax_copy_attribute(el, "AXTitle") or ax_copy_attribute(el, "AXDescription") or ""
    )
    return str(name).strip()


def press_menu_labels(pid: int, labels: list[str], settle_sec: float = 0.25) -> bool:
    """Navigate the menubar by a label chain (e.g. ["文件", "新建标签页"]),
    pressing each level so lazily-populated submenus materialize."""
    HS = _hs()
    app_el = HS.AXUIElementCreateApplication(pid)
    bar = ax_copy_attribute(app_el, "AXMenuBar")
    if bar is None or not labels:
        return False

    current = ax_copy_attribute(bar, "AXChildren") or []
    for depth, label in enumerate(labels):
        target = None
        for el in current:
            role = str(ax_copy_attribute(el, "AXRole") or "")
            if role not in ("AXMenuBarItem", "AXMenuItem"):
                continue
            if _menu_label(el) == label:
                target = el
                break
        if target is None:
            logger.debug(f"[ax] menu label not found at depth {depth}: {label!r}")
            return False
        err, action_names = HS.AXUIElementCopyActionNames(target, None)
        actions = [str(a) for a in action_names] if err == 0 and action_names else []
        action = (
            "AXPress"
            if "AXPress" in actions
            else ("AXPick" if "AXPick" in actions else None)
        )
        if action is None:
            return False
        if HS.AXUIElementPerformAction(target, action) != 0:
            return False
        time.sleep(settle_sec)
        current = _menu_children(target)
    return True


def ensure_pid(bundle_id: str) -> int | None:
    """Focus-free app launch + window materialization (§四十一 recipe)."""
    return ensure_app_running(bundle_id)
