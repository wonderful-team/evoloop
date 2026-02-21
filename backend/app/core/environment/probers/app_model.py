"""
AppModel - Application Structure Model.

Defines the core data structures that represent an application's UI topology:
  - UIElement: A semantic anchor for a single interactive element.
  - AppStateNode: A snapshot of the application at a given moment.
  - StateTransition: A record of how one state leads to another.
  - AppModel: The complete structural map of an application.

These structures are produced via DynamicSpecialistNode
and consumed by various reconnaissance and verification agents.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class UIElement:
    """
    A semantic anchor for a single interactive UI element.

    Combines multiple identification strategies so that PreActionVerifier
    can locate the element even after minor UI changes:
    - ax_path: Primary structural identifier from AccessibilityTree
    - label:   Human-readable text of the element (OCR fallback)
    - visual_hash: pHash of the element's bounding region for visual drift detection
    """

    role: str                        # "AXButton", "AXTextField", "AXMenuItem"
    label: str                       # "Save", "New Connection...", "File"
    ax_path: str                     # "Window[0].Toolbar.Button['Save']"
    shortcut: str | None = None      # "⌘S", "Ctrl+N"
    visual_hash: str | None = None   # pHash of 32x32 pixel region around element
    bounds: dict | None = None       # {"x": 10, "y": 20, "width": 80, "height": 30}
    is_enabled: bool = True
    parent_menu: str | None = None   # For menu items, the parent menu name

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "label": self.label,
            "ax_path": self.ax_path,
            "shortcut": self.shortcut,
            "visual_hash": self.visual_hash,
            "bounds": self.bounds,
            "is_enabled": self.is_enabled,
            "parent_menu": self.parent_menu,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UIElement":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AppStateNode:
    """
    A snapshot of the application at a given UI state (a 'screen').

    state_id is a stable, semantic identifier (e.g., "navicat_main_window"),
    not a numeric index, so it can be referenced across exploration sessions.
    """

    state_id: str                           # Unique semantic ID, e.g. "navicat_main_window"
    window_title: str                       # Exact window title string
    elements: list[UIElement] = field(default_factory=list)
    screenshot_hash: str | None = None      # pHash of full screenshot for fast drift detection
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_element_by_label(self, label: str) -> UIElement | None:
        """Find an element by its display label (case-insensitive)."""
        label_lower = label.lower()
        return next(
            (e for e in self.elements if e.label.lower() == label_lower), None
        )

    def get_element_by_ax_path(self, ax_path: str) -> UIElement | None:
        """Find an element by its AX path."""
        return next((e for e in self.elements if e.ax_path == ax_path), None)

    def to_dict(self) -> dict:
        return {
            "state_id": self.state_id,
            "window_title": self.window_title,
            "elements": [e.to_dict() for e in self.elements],
            "screenshot_hash": self.screenshot_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppStateNode":
        elements = [UIElement.from_dict(e) for e in data.get("elements", [])]
        return cls(
            state_id=data["state_id"],
            window_title=data["window_title"],
            elements=elements,
            screenshot_hash=data.get("screenshot_hash"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class StateTransition:
    """
    Records a causal link: performing `action` on `from_state` leads to `to_state`.

    This builds the state-transition graph of the application, which
    used to generate multi-step Navigation maps and Skills.
    """

    from_state: str          # state_id of the source state
    action: UIElement        # The element that was interacted with
    to_state: str            # state_id of the resulting state
    action_type: str = "click"     # "click", "type", "scroll", "shortcut"
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "from_state": self.from_state,
            "action": self.action.to_dict(),
            "to_state": self.to_state,
            "action_type": self.action_type,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StateTransition":
        return cls(
            from_state=data["from_state"],
            action=UIElement.from_dict(data["action"]),
            to_state=data["to_state"],
            action_type=data.get("action_type", "click"),
            success=data.get("success", True),
        )


@dataclass
class AppModel:
    """
    The complete structural map of an application.

    This is the primary output of application exploration.
    It is serialized to JSON and stored in long-term memory (Brain)
    under the concept key: "app_model:<bundle_id>".

    The version_hash allows the system to detect when the application
    has been updated and the AppModel needs to be refreshed.
    """

    app_name: str                                           # "Navicat Premium"
    bundle_id: str                                          # "com.navicat.NavicatPremium"
    platform: str                                           # "macos" or "android"
    states: dict[str, AppStateNode] = field(default_factory=dict)
    transitions: list[StateTransition] = field(default_factory=list)
    menu_tree: dict[str, Any] = field(default_factory=dict)   # Full menu hierarchy
    version_hash: str = ""                                  # Hash of app binary/version for drift detection
    explored_at: datetime = field(default_factory=datetime.now)
    exploration_depth: int = 0                              # How many levels deep we explored

    @property
    def concept_key(self) -> str:
        """The long-term memory key for this AppModel."""
        return f"app_model:{self.bundle_id}"

    def compute_version_hash(self, app_version: str, app_modified_at: str) -> str:
        """Generate a stable hash from app version info for drift detection."""
        raw = f"{self.bundle_id}:{app_version}:{app_modified_at}"
        self.version_hash = hashlib.md5(raw.encode()).hexdigest()[:12]
        return self.version_hash

    def add_state(self, state: AppStateNode) -> None:
        self.states[state.state_id] = state

    def add_transition(self, transition: StateTransition) -> None:
        self.transitions.append(transition)

    def get_all_elements(self) -> list[UIElement]:
        """Flatten all elements from all states."""
        elements = []
        for state in self.states.values():
            elements.extend(state.elements)
        return elements

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "bundle_id": self.bundle_id,
            "platform": self.platform,
            "states": {k: v.to_dict() for k, v in self.states.items()},
            "transitions": [t.to_dict() for t in self.transitions],
            "menu_tree": self.menu_tree,
            "version_hash": self.version_hash,
            "explored_at": self.explored_at.isoformat(),
            "exploration_depth": self.exploration_depth,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "AppModel":
        states = {
            k: AppStateNode.from_dict(v) for k, v in data.get("states", {}).items()
        }
        transitions = [
            StateTransition.from_dict(t) for t in data.get("transitions", [])
        ]
        return cls(
            app_name=data["app_name"],
            bundle_id=data["bundle_id"],
            platform=data.get("platform", "macos"),
            states=states,
            transitions=transitions,
            menu_tree=data.get("menu_tree", {}),
            version_hash=data.get("version_hash", ""),
            explored_at=datetime.fromisoformat(data["explored_at"]) if "explored_at" in data else datetime.now(),
            exploration_depth=data.get("exploration_depth", 0),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AppModel":
        return cls.from_dict(json.loads(json_str))
