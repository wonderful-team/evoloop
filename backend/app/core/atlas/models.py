"""
App Atlas Data Models - Core platform-agnostic UI structures.

Defines the core data structures that represent an application's UI topology:
  - AtlasElement: A semantic anchor for a single interactive element.
  - AtlasState: A snapshot of the application at a given moment.
  - AtlasTransition: A record of how one state leads to another.
  - AtlasApp: The complete structural map of an application.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.utils.dataclass_helpers import NestedSerializableMixin
from app.utils.hash import compute_version_hash as _compute_version_hash


@dataclass
class AtlasElement(NestedSerializableMixin):
    """
    A semantic anchor for a single interactive UI element.
    Platform-agnostic representation.

    Element Classification
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

    # Element classification
    element_category: str = "unknown"  # static | static_navigation | static_toolbar | dynamic | dynamic_content | container_*
    is_infrastructure: bool = False     # True for reliable static elements
    coordinate_confidence: float = 1.0  # 0.0-1.0, reliability of coordinates
    clickable: bool = False             # Whether element is interactive
    metadata: dict[str, Any] = field(default_factory=dict)  # Platform-specific metadata


@dataclass
class AtlasState(NestedSerializableMixin):
    """
    A snapshot of the application at a given UI state (a 'screen').

    Infrastructure-only states
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


@dataclass
class AtlasTransition(NestedSerializableMixin):
    """
    Records a causal link between states.
    """
    from_state: str
    action: AtlasElement
    to_state: str
    action_type: str = "click"
    success: bool = True


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
    def all_elements(self) -> list[AtlasElement]:
        """Flatten all elements from all states."""
        elements = []
        for state in self.states.values():
            elements.extend(state.elements)
        return elements

    @property
    def infrastructure_elements(self) -> list[AtlasElement]:
        """Get only infrastructure (static) elements."""
        return [e for e in self.all_elements if e.is_infrastructure]

    @property
    def dynamic_elements(self) -> list[AtlasElement]:
        """Get only dynamic elements."""
        return [e for e in self.all_elements if not e.is_infrastructure]

    def get_element_by_label(self, label: str) -> AtlasElement | None:
        """Search for an element by label across all states."""
        label_lower = label.lower()
        for state in self.states.values():
            if elem := state.get_element_by_label(label):
                return elem
        return None

    def get_element_by_path(self, ax_path: str) -> AtlasElement | None:
        """Search for an element by path across all states."""
        for state in self.states.values():
            if elem := state.get_element_by_path(ax_path):
                return elem
        return None

    def get_state_elements(self, state_id: str) -> list[AtlasElement]:
        """Get elements for a specific state."""
        if state := self.states.get(state_id):
            return state.elements
        return []

    def to_dict(self) -> dict:
        """Convert to dictionary with proper datetime handling."""
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
        """Create from dictionary with proper datetime handling."""
        states = {
            k: AtlasState.from_dict(v) for k, v in data.get("states", {}).items()
        }
        transitions = [
            AtlasTransition.from_dict(t) for t in data.get("transitions", [])
        ]
        
        # Handle datetime parsing
        explored_at = datetime.now()
        if "explored_at" in data:
            try:
                explored_at = datetime.fromisoformat(data["explored_at"])
            except (ValueError, TypeError):
                pass
        
        return cls(
            app_name=data["app_name"],
            bundle_id=data["bundle_id"],
            platform=data.get("platform", "macos"),
            states=states,
            transitions=transitions,
            menu_tree=data.get("menu_tree", {}),
            version_hash=data.get("version_hash", ""),
            explored_at=explored_at,
            exploration_depth=data.get("exploration_depth", 0),
            is_dynamic=data.get("is_dynamic", False),
        )

    def compute_version_hash(self, version_name: str | None = None, update_time: str | None = None) -> str:
        """
        Compute a hash representing the current state of the app map.
        Includes version metadata if provided.
        """
        content = f"{self.bundle_id}:{version_name or ''}:{update_time or ''}:{len(self.states)}:{len(self.transitions)}"
        return _compute_version_hash(content)

    def get_infrastructure_only(self) -> "AtlasApp":
        """
        Return a copy with only infrastructure (static) elements.
        Used for dynamic apps where only static UI is reliable.
        """
        filtered_states = {}
        for state_id, state in self.states.items():
            infra_elements = [e for e in state.elements if e.is_infrastructure]
            if infra_elements:
                # Create new state with filtered elements
                filtered_state = AtlasState(
                    state_id=state.state_id,
                    window_title=state.window_title,
                    elements=infra_elements,
                    screenshot_hash=state.screenshot_hash,
                    metadata=state.metadata,
                    is_infrastructure_only=True,
                )
                filtered_states[state_id] = filtered_state

        return AtlasApp(
            app_name=self.app_name,
            bundle_id=self.bundle_id,
            platform=self.platform,
            states=filtered_states,
            transitions=[],  # Clear transitions for infrastructure-only view
            menu_tree=self.menu_tree,
            version_hash=self.version_hash,
            explored_at=self.explored_at,
            exploration_depth=self.exploration_depth,
            is_dynamic=True,  # Mark as dynamic since we're filtering
        )
