"""
Atlas Native Surveyor (M2) - active, focus-free AX surveying for macOS apps.

Produces AtlasApp maps (states + transitions + menubar) into the Atlas store.

Hard rules baked in (design doc v0.3 / verification §四十一-四十二):
- Dump by pid via AXUIElementCreateApplication — focus never stolen.
- Every element carries its AXActions list (AXUIElementCopyActionNames).
- Menubar and window regions are surveyed and scored SEPARATELY.
- State identity = structural signature (set of (role,name,path) of named
  elements), NOT window title — titles drift with document names.
- Exploration is opt-in per app and clicks only navigation roles whose label
  passes the action blacklist (quit/delete/erase... labels: record, never click).
- Storage MERGES by state_id (no more whole-app wipe on every observation).

The ONLY function touching HIServices element objects is `dump_app_elements`
(plus `_locate`/`press_at_path` for exploration) — unit tests mock these.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.atlas.ax_actions import activate_at_path
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState, AtlasTransition
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.schemas import MenuItem, MenuTree, Rect

logger = logging.getLogger(__name__)

MAX_DEPTH = 12
MENUBAR_STATE_ID = "__menubar__"
RESURVEY_JACCARD_THRESHOLD = 0.8

INTERACTIVE_ROLES = {
    "AXButton", "AXTextField", "AXTextArea", "AXMenuItem", "AXMenuBarItem",
    "AXCheckBox", "AXRadioButton", "AXSlider", "AXPopUpButton", "AXComboBox",
    "AXTab", "AXTabGroup", "AXLink", "AXSwitch", "AXStepper", "AXSearchField",
    "AXIncrementor", "AXValueIndicator", "AXOutline", "AXTable", "AXRow",
}

# Labels that must NEVER be clicked during exploration (recorded, not triggered).
ACTION_BLACKLIST = re.compile(
    r"quit|退出|log ?out|登出|sign out|delete|删除|清空|erase|抹掉|force quit|强制退出"
    r"|close all|全部关闭|remove|移除|trash|废纸篓|reset|重置|format|格式化"
    r"|empty|倒空|restore|还原|恢复出厂|uninstall|卸载|deactivat|注销|关机|shutdown|restart|重启",
    re.IGNORECASE,
)


@dataclass
class SurveyPolicy:
    """Per-app exploration policy. Read-only by default."""

    explore: bool = False
    explore_roles: set[str] = field(default_factory=lambda: {"AXRow", "AXTab"})
    max_clicks: int = 15
    click_settle_sec: float = 0.7


@dataclass
class SurveyCoverage:
    window: dict = field(default_factory=dict)
    menubar: dict = field(default_factory=dict)
    tier: str = "C"
    menu_reachable_pct: float = 0.0


@dataclass
class SurveyResult:
    bundle_id: str
    app: AtlasApp | None = None
    coverage: SurveyCoverage = field(default_factory=SurveyCoverage)
    fingerprints: dict[str, frozenset] = field(default_factory=dict)
    transitions_found: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# AX access layer (the only HIServices-touching code — mocked in tests)
# ---------------------------------------------------------------------------


def dump_app_elements(pid: int) -> dict[str, list[dict]]:
    """Dump window + menubar elements of a running app. Focus-free.

    Each element: {role, name, path, bounds, actions, enabled, shortcut}.
    """
    import HIServices

    from app.infrastructure.drivers.macos._workspace import (
        ax_copy_attribute,
        ax_value_point,
        ax_value_size,
    )

    def collect(root: Any, path: str, depth: int, out: list[dict]) -> None:
        if depth > MAX_DEPTH:
            return
        role = str(ax_copy_attribute(root, "AXRole") or "AXUnknown")
        name = (
            ax_copy_attribute(root, "AXTitle")
            or ax_copy_attribute(root, "AXDescription")
            or ax_copy_attribute(root, "AXValue")
            or ""
        )
        pos = ax_value_point(ax_copy_attribute(root, "AXPosition"))
        size = ax_value_size(ax_copy_attribute(root, "AXSize"))
        err, action_names = HIServices.AXUIElementCopyActionNames(root, None)
        actions = [str(a) for a in action_names] if err == 0 and action_names else []
        enabled_raw = ax_copy_attribute(root, "AXEnabled")
        shortcut = ax_copy_attribute(root, "AXMenuItemCmdChar") or ""
        out.append(
            {
                "role": role,
                "name": str(name) if name else "",
                "path": path,
                "bounds": [pos[0], pos[1], size[0], size[1]] if pos and size else [0, 0, 0, 0],
                "actions": actions,
                "enabled": bool(enabled_raw) if enabled_raw is not None else True,
                "shortcut": str(shortcut),
            }
        )
        for i, child in enumerate(ax_copy_attribute(root, "AXChildren") or []):
            collect(child, f"{path} > {role} {i + 1}", depth + 1, out)

    app_el = HIServices.AXUIElementCreateApplication(pid)
    windows: list[dict] = []
    for i, w in enumerate(ax_copy_attribute(app_el, "AXWindows") or []):
        collect(w, f"window {i + 1}", 0, windows)
    menubar: list[dict] = []
    bar = ax_copy_attribute(app_el, "AXMenuBar")
    if bar is not None:
        collect(bar, "menubar", 0, menubar)
    return {"windows": windows, "menubar": menubar}


# press/activate primitives live in ax_actions; exploration injects
# activate_at_path as the default press_fn.


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def element_signature(elements: list[dict]) -> frozenset:
    """Structural fingerprint of a state (M1 recipe)."""
    return frozenset(
        (e["role"], e["name"].strip(), e["path"]) for e in elements if e["name"].strip()
    )


def signature_state_id(sig: frozenset) -> str:
    h = hashlib.sha1("|".join(sorted(f"{r}|{n}|{p}" for r, n, p in sig)).encode()).hexdigest()[:10]
    return f"sig_{h}"


def jaccard(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / max(1, len(union))


def is_blacklisted(label: str) -> bool:
    return bool(label.strip()) and bool(ACTION_BLACKLIST.search(label))


def effective_labels(elements: list[dict]) -> dict[str, str]:
    """path -> display label. Container rows (AXRow/AXCell) are unnamed in
    macOS — the label lives in a named descendant (e.g. AXStaticText)."""
    labels = {e["path"]: e["name"].strip() for e in elements}
    for e in elements:
        if labels[e["path"]]:
            continue
        prefix = e["path"] + " > "
        for d in elements:
            if d["path"].startswith(prefix) and d["name"].strip():
                labels[e["path"]] = d["name"].strip()
                break
    return labels


def coverage_metrics(elements: list[dict]) -> dict:
    total = len(elements)
    named = [e for e in elements if e["name"].strip()]
    interactive = [e for e in elements if e["role"] in INTERACTIVE_ROLES]
    interactive_named = [e for e in interactive if e["name"].strip()]
    menu = [e for e in elements if e["role"] in ("AXMenuItem", "AXMenuBarItem")]
    zero = [e for e in elements if e["bounds"][2:] == [0, 0]]
    return {
        "total": total,
        "named_pct": round(100 * len(named) / max(1, total)),
        "interactive": len(interactive),
        "interactive_named": len(interactive_named),
        "menu": len(menu),
        "zero_bounds_pct": round(100 * len(zero) / max(1, total)),
    }


def coverage_tier(window_metrics: dict) -> str:
    if window_metrics["interactive_named"] >= 15 and window_metrics["named_pct"] >= 30:
        return "A"
    if window_metrics["interactive_named"] >= 5 or window_metrics["menu"] >= 10:
        return "B"
    return "C"


def build_menubar_state(menubar_elements: list[dict]) -> AtlasState:
    """Menubar persisted as a dedicated state (no schema migration); each menu
    item keeps its menubar ax_path, parent breadcrumb and shortcut."""
    elements: list[AtlasElement] = []
    for e in menubar_elements:
        if e["role"] not in ("AXMenuItem", "AXMenuBarItem") or not e["name"].strip():
            continue
        parts = [p.strip() for p in e["path"].split(">")]
        parent = parts[-2] if len(parts) >= 2 else ""
        elements.append(
            AtlasElement(
                role=e["role"],
                label=e["name"].strip(),
                ax_path=e["path"],
                bounds=Rect.model_validate(e["bounds"]),
                clickable=bool(e["actions"]),
                is_enabled=e["enabled"],
                parent_menu=parent,
                shortcut=e["shortcut"] or None,
                element_category="static_navigation",
                is_infrastructure=True,
                metadata={"extra": {"actions": e["actions"], "region": "menubar"}},
            )
        )
    return AtlasState(
        state_id=MENUBAR_STATE_ID,
        window_title="__menubar__",
        elements=elements,
        is_infrastructure_only=True,
    )


def build_menu_tree(menubar_elements: list[dict]) -> MenuTree:
    """In-memory MenuTree for the generator (M3). AXMenu containers are
    skipped — an item's parent is its nearest MENU ITEM ancestor."""
    items = {
        e["path"]: e
        for e in menubar_elements
        if e["role"] in ("AXMenuItem", "AXMenuBarItem") and e["name"].strip()
    }

    def parent_item(path: str) -> str | None:
        p = path
        while " > " in p:
            p = p.rsplit(" > ", 1)[0]
            if p in items:
                return p
        return None

    children: dict[str, list[dict]] = {}
    tops: list[dict] = []
    for path, e in items.items():
        par = parent_item(path)
        if par is None:
            tops.append(e)
        else:
            children.setdefault(par, []).append(e)

    def to_item(e: dict) -> MenuItem:
        kids = [to_item(c) for c in children.get(e["path"], [])]
        action = e["actions"][0] if e["actions"] else None
        if e["shortcut"]:
            action = f"{action or ''}|cmd:{e['shortcut']}"
        return MenuItem(label=e["name"].strip(), action=action, children=kids)

    return MenuTree(menus=[to_item(e) for e in tops])


def menu_reachable_pct(menubar_elements: list[dict]) -> float:
    """Reachable = named AND actionable. Unnamed AXMenuItems are separators —
    on modern macOS they DO carry actions (verified via System Events), so
    name, not action list, identifies them."""
    items = [
        e
        for e in menubar_elements
        if e["role"] in ("AXMenuItem", "AXMenuBarItem") and e["name"].strip()
    ]
    if not items:
        return 0.0
    reachable = [e for e in items if e["actions"] or e["role"] == "AXMenuBarItem"]
    return round(100 * len(reachable) / len(items), 1)


def _to_atlas_element(e: dict) -> AtlasElement:
    return AtlasElement(
        role=e["role"],
        label=e["name"].strip(),
        ax_path=e["path"],
        bounds=Rect.model_validate(e["bounds"]),
        clickable=e["role"] in INTERACTIVE_ROLES or bool(e["actions"]),
        is_enabled=e["enabled"],
        metadata={"extra": {"actions": e["actions"], "region": "window"}},
    )


# ---------------------------------------------------------------------------
# Surveyor
# ---------------------------------------------------------------------------


class AtlasSurveyor:
    """Active surveyor: launch (focus-free) -> snapshot -> optional explore ->
    merge-save into the Atlas store."""

    def __init__(self, store: IAtlasStore | None = None):
        if store is None:
            from app.core.atlas.adapters.sql_store import SQLAtlasStore

            store = SQLAtlasStore()
        self.store = store

    async def survey_app(
        self,
        bundle_id: str,
        app_name: str | None = None,
        platform: str = "macos",
        policy: SurveyPolicy | None = None,
        dump_fn=dump_app_elements,
        press_fn=activate_at_path,
    ) -> SurveyResult:
        from app.infrastructure.drivers.macos._workspace import ensure_app_running

        policy = policy or SurveyPolicy()
        result = SurveyResult(bundle_id=bundle_id)
        pid = await asyncio.to_thread(ensure_app_running, bundle_id)
        if pid is None:
            result.error = "launch failed"
            return result

        states: dict[str, AtlasState] = {}
        transitions: list[AtlasTransition] = []
        fingerprints: dict[str, frozenset] = {}
        tried: set[tuple[str, str]] = set()
        clicks = 0

        def snapshot() -> tuple[str, list[dict], dict[str, list[dict]]]:
            dump = dump_fn(pid)
            sig = element_signature(dump["windows"])
            sid = signature_state_id(sig)
            return sid, dump["windows"], dump

        sid, win_elements, dump = snapshot()
        while True:
            if sid not in states:
                sig = element_signature(win_elements)
                fingerprints[sid] = sig
                states[sid] = AtlasState(
                    state_id=sid,
                    window_title=self._window_title(win_elements),
                    elements=[_to_atlas_element(e) for e in win_elements],
                )
            if not policy.explore or clicks >= policy.max_clicks:
                break
            labels = effective_labels(win_elements)
            target = self._pick_explore_target(win_elements, sid, tried, policy, labels)
            if target is None:
                break
            tried.add((sid, target["path"]))
            prev_sid = sid
            ok = await asyncio.to_thread(press_fn, pid, target["path"])
            clicks += 1
            await asyncio.sleep(policy.click_settle_sec)
            sid, win_elements, dump = snapshot()
            if ok and sid != prev_sid:
                action_el = _to_atlas_element(target)
                action_el.label = labels.get(target["path"], target["name"].strip())
                transitions.append(
                    AtlasTransition(
                        from_state=prev_sid,
                        action=action_el,
                        to_state=sid,
                        action_type="click",
                    )
                )

        menubar = dump["menubar"]
        states[MENUBAR_STATE_ID] = build_menubar_state(menubar)

        app = AtlasApp(
            app_name=app_name or bundle_id,
            bundle_id=bundle_id,
            platform=platform,
            states=states,
            transitions=transitions,
            menu_tree=build_menu_tree(menubar),
        )
        app.version_hash = app.compute_version_hash()

        wm = coverage_metrics(dump["windows"])
        mm = coverage_metrics(menubar)
        result.coverage = SurveyCoverage(
            window=wm,
            menubar=mm,
            tier=coverage_tier(wm),
            menu_reachable_pct=menu_reachable_pct(menubar),
        )
        result.fingerprints = fingerprints
        result.transitions_found = len(transitions)
        result.app = app

        merged = await self._merge_existing(app)
        await self.store.save_app_model(merged)
        logger.info(
            f"[Surveyor] {bundle_id}: {len(states)} states "
            f"({len(transitions)} transitions, tier={result.coverage.tier}, "
            f"menu_reachable={result.coverage.menu_reachable_pct}%)"
        )
        return result

    async def needs_resurvey(self, bundle_id: str, platform: str = "macos") -> bool:
        """True when the live window fingerprint drifts beyond Jaccard 0.8 from
        ALL stored states (i.e. the map no longer matches reality)."""
        from app.infrastructure.drivers.macos._workspace import running_pid_for_bundle

        pid = running_pid_for_bundle(bundle_id)
        if pid is None:
            return True
        summary = await self.store.get_app_summary(bundle_id, platform=platform)
        if not summary or not summary.states:
            return True
        live = element_signature(dump_app_elements(pid)["windows"])
        for entry in summary.states:
            state_id = entry.get("id") if isinstance(entry, dict) else entry
            if not state_id or state_id == MENUBAR_STATE_ID:
                continue
            detail = await self.store.get_state_detail(bundle_id, state_id, platform=platform)
            if not detail:
                continue
            stored = frozenset(
                (str(e.get("role", "")), str(e.get("label", "")).strip(), str(e.get("ax_path", "")))
                for e in detail.elements
                if str(e.get("label", "")).strip()
            )
            if stored and jaccard(live, stored) >= RESURVEY_JACCARD_THRESHOLD:
                return False
        return True

    async def _merge_existing(self, app: AtlasApp) -> AtlasApp:
        """Keep historical states/transitions that this survey did not observe
        (states matched by state_id are replaced with fresh data)."""
        summary = await self.store.get_app_summary(app.bundle_id, platform=app.platform)
        if not summary:
            return app
        for entry in summary.states:
            state_id = entry.get("id") if isinstance(entry, dict) else entry
            if not state_id or state_id in app.states:
                continue
            detail = await self.store.get_state_detail(app.bundle_id, state_id, platform=app.platform)
            if not detail:
                continue
            elements = [AtlasElement.model_validate(e) for e in detail.elements]
            app.states[state_id] = AtlasState(
                state_id=state_id,
                window_title=detail.window_title or "",
                elements=elements,
                is_infrastructure_only=state_id == MENUBAR_STATE_ID,
            )
        existing_transitions = await self.store.get_transitions_summary(app.bundle_id, platform=app.platform)
        seen = {(t.from_state, t.action.label, t.to_state) for t in app.transitions}
        for t in existing_transitions:
            key = (t.get("from_state", ""), t.get("label", ""), t.get("to_state", ""))
            if key in seen:
                continue
            app.transitions.append(
                AtlasTransition(
                    from_state=key[0],
                    action=AtlasElement(label=key[1]),
                    to_state=key[2],
                    action_type=t.get("type", "click"),
                )
            )
        return app

    @staticmethod
    def _window_title(elements: list[dict]) -> str:
        for e in elements:
            if e["role"] == "AXWindow" and e["name"].strip():
                return e["name"].strip()
        return ""

    @staticmethod
    def _pick_explore_target(
        elements: list[dict],
        sid: str,
        tried: set[tuple[str, str]],
        policy: SurveyPolicy,
        labels: dict[str, str] | None = None,
    ) -> dict | None:
        labels = labels or {}
        for e in elements:
            if e["role"] not in policy.explore_roles:
                continue
            label = labels.get(e["path"], e["name"].strip())
            if not label or not e["enabled"]:
                continue
            if is_blacklisted(label):
                continue
            if (sid, e["path"]) in tried:
                continue
            return e
        return None
