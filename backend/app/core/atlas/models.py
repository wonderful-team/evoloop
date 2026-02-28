"""
App Atlas Data Models - Core platform-agnostic UI structures.

Defines the core data structures that represent an application's UI topology:
  - AtlasElement: A semantic anchor for a single interactive element.
  - AtlasState: A snapshot of the application at a given moment.
  - AtlasTransition: A record of how one state leads to another.
  - AtlasApp: The complete structural map of an application.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AtlasElement:
    """
    A semantic anchor for a single interactive UI element.
    Platform-agnostic representation.

    Phase 6: Element Classification
    - element_category: Classifies element type (static/dynamic/container)
    - is_infrastructure: True for static elements like toolbars (reliable coordinates)
    - coordinate_confidence: 0.0-1.0, low for dynamic content
    """
    role: str = ""                   # e.g., "BUTTON", "INPUT", "AXButton"
    label: str = ""                  # e.g., "Save", "File"
    ax_path: str = ""                # Primary structural path/locator (Legacy/macOS specific)
    os_identifier: str | None = None # Cross-platform OS identifier (e.g., Android viewId, Windows AutomationId)
    ocr_confidence: float | None = None # Vision/OCR confidence score
    shortcut: str | None = None
    visual_hash: str | None = None
    bounds: dict[str, int] | None = None
    is_enabled: bool = True
    parent_menu: str | None = None

    # Phase 6: Element classification
    element_category: str = "unknown"  # static | static_navigation | static_toolbar | dynamic | dynamic_content | container_*
    is_infrastructure: bool = False     # True for reliable static elements
    coordinate_confidence: float = 1.0  # 0.0-1.0, reliability of coordinates
    clickable: bool = False             # Whether element is interactive
    metadata: dict[str, Any] = field(default_factory=dict)  # Platform-specific metadata

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "label": self.label,
            "ax_path": self.ax_path,
            "os_identifier": self.os_identifier or self.ax_path,
            "ocr_confidence": self.ocr_confidence,
            "shortcut": self.shortcut,
            "visual_hash": self.visual_hash,
            "bounds": self.bounds,
            "is_enabled": self.is_enabled,
            "parent_menu": self.parent_menu,
            "element_category": self.element_category,
            "is_infrastructure": self.is_infrastructure,
            "coordinate_confidence": self.coordinate_confidence,
            "clickable": self.clickable,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AtlasElement:
        # Filter only valid fields
        valid_fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class AtlasState:
    """
    A snapshot of the application at a given UI state (a 'screen').

    Phase 6: Infrastructure-only states
    - is_infrastructure_only: True for dynamic apps (only stores static UI like toolbars)
    """
    state_id: str
    window_title: str
    elements: list[AtlasElement] = field(default_factory=list)
    screenshot_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Phase 6: Mark if this state only contains infrastructure elements
    is_infrastructure_only: bool = False

    def get_element_by_label(self, label: str) -> AtlasElement | None:
        label_lower = label.lower()
        return next((e for e in self.elements if e.label.lower() == label_lower), None)

    def get_element_by_path(self, ax_path: str) -> AtlasElement | None:
        return next((e for e in self.elements if e.ax_path == ax_path), None)

    def to_dict(self) -> dict:
        return {
            "state_id": self.state_id,
            "window_title": self.window_title,
            "elements": [e.to_dict() for e in self.elements],
            "screenshot_hash": self.screenshot_hash,
            "metadata": self.metadata,
            "is_infrastructure_only": self.is_infrastructure_only,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AtlasState:
        elements = [AtlasElement.from_dict(e) for e in data.get("elements", [])]
        return cls(
            state_id=data["state_id"],
            window_title=data["window_title"],
            elements=elements,
            screenshot_hash=data.get("screenshot_hash"),
            metadata=data.get("metadata", {}),
            is_infrastructure_only=data.get("is_infrastructure_only", False),
        )


@dataclass
class AtlasTransition:
    """
    Records a causal link between states.
    """
    from_state: str
    action: AtlasElement
    to_state: str
    action_type: str = "click"
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
    def from_dict(cls, data: dict) -> AtlasTransition:
        return cls(
            from_state=data["from_state"],
            action=AtlasElement.from_dict(data["action"]),
            to_state=data["to_state"],
            action_type=data.get("action_type", "click"),
            success=data.get("success", True),
        )


@dataclass
class AtlasApp:
    """
    The complete structural map of an application.

    Phase 6: Dynamic app marking
    - is_dynamic: True for coordinate-unstable apps (WeChat, browsers, etc)
    """
    app_name: str
    bundle_id: str
    platform: str
    states: dict[str, AtlasState] = field(default_factory=dict)
    transitions: list[AtlasTransition] = field(default_factory=list)
    menu_tree: dict[str, Any] = field(default_factory=dict)
    version_hash: str = ""
    explored_at: datetime = field(default_factory=datetime.now)
    exploration_depth: int = 0

    # Phase 6: Mark if this is a coordinate-unstable dynamic app
    is_dynamic: bool = False

    @property
    def concept_key(self) -> str:
        return f"app_model:{self.bundle_id}"

    def compute_version_hash(self, app_version: str, app_modified_at: str) -> str:
        raw = f"{self.bundle_id}:{app_version}:{app_modified_at}"
        self.version_hash = hashlib.md5(raw.encode()).hexdigest()[:12]
        return self.version_hash

    def add_state(self, state: AtlasState) -> None:
        self.states[state.state_id] = state

    def add_transition(self, transition: AtlasTransition) -> None:
        self.transitions.append(transition)

    def get_all_elements(self) -> list[AtlasElement]:
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
            "is_dynamic": self.is_dynamic,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> AtlasApp:
        states = {
            k: AtlasState.from_dict(v) for k, v in data.get("states", {}).items()
        }
        transitions = [
            AtlasTransition.from_dict(t) for t in data.get("transitions", [])
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
            is_dynamic=data.get("is_dynamic", False),
        )

    @classmethod
    def from_json(cls, json_str: str) -> AtlasApp:
        return cls.from_dict(json.loads(json_str))
