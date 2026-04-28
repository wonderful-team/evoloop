"""
App Atlas Data Models - Core platform-agnostic UI structures.

Defines the core data structures that represent an application's UI topology:
  - AtlasElement: A semantic anchor for a single interactive element.
  - AtlasState: A snapshot of the application at a given moment.
  - AtlasTransition: A record of how one state leads to another.
  - AtlasApp: The complete structural map of an application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.atlas.schemas import AtlasStateMetadata, MenuItem, MenuTree, Rect, ElementMetadata

class AtlasElement(DynamicBaseModel):
    """
    A semantic anchor for a single interactive UI element.
    Platform-agnostic representation.
    """
    role: str = ""                   # e.g., "BUTTON", "INPUT", "AXButton"
    label: str = ""                  # e.g., "Save", "File"
    ax_path: str = ""                # Primary structural path/locator (Legacy/macOS specific)
    os_identifier: str | None = None # Cross-platform OS identifier
    ocr_confidence: float | None = None # Vision/OCR confidence score
    shortcut: str | None = None
    visual_hash: str | None = None
    bounds: Rect | None = None
    is_enabled: bool = True
    parent_menu: str | None = None

    # Element classification
    element_category: str = "unknown"  # static | dynamic | container_*
    is_infrastructure: bool = False     # True for reliable static elements
    coordinate_confidence: float = 1.0  # 0.0-1.0
    clickable: bool = False             # Whether element is interactive
    metadata: ElementMetadata = Field(default_factory=ElementMetadata)

    def to_dict(self) -> dict:
        """Legacy compatibility method."""
        return self.model_dump(by_alias=True)

    @classmethod
    def from_dict(cls, data: dict) -> AtlasElement:
        """Legacy compatibility method."""
        return cls.model_validate(data)


class AtlasState(DynamicBaseModel):
    """
    A snapshot of the application at a given UI state (a 'screen').
    """
    state_id: str
    window_title: str
    elements: list[AtlasElement] = Field(default_factory=list)
    screenshot_hash: str | None = None
    metadata: AtlasStateMetadata = Field(default_factory=AtlasStateMetadata)
    is_infrastructure_only: bool = False

    def get_element_by_label(self, label: str) -> AtlasElement | None:
        label_lower = label.lower()
        return next((e for e in self.elements if e.label.lower() == label_lower), None)

    def get_element_by_path(self, ax_path: str) -> AtlasElement | None:
        return next((e for e in self.elements if e.ax_path == ax_path), None)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> AtlasState:
        return cls.model_validate(data)


class AtlasTransition(DynamicBaseModel):
    """
    Records a causal link between states.
    """
    from_state: str
    action: AtlasElement
    to_state: str
    action_type: str = "click"
    success: bool = True

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> AtlasTransition:
        return cls.model_validate(data)


class AtlasApp(DynamicBaseModel):
    """
    The complete structural map of an application.
    """
    app_name: str
    bundle_id: str
    platform: str
    states: dict[str, AtlasState] = Field(default_factory=dict)
    transitions: list[AtlasTransition] = Field(default_factory=list)
    menu_tree: MenuTree = Field(default_factory=MenuTree)
    version_hash: str = ""
    explored_at: datetime = Field(default_factory=datetime.now)
    exploration_depth: int = 0
    is_dynamic: bool = False

    @property
    def all_elements(self) -> list[AtlasElement]:
        elements = []
        for state in self.states.values():
            elements.extend(state.elements)
        return elements

    @property
    def infrastructure_elements(self) -> list[AtlasElement]:
        return [e for e in self.all_elements if e.is_infrastructure]

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

    def compute_version_hash(self, version_name: str | None = None, update_time: str | None = None) -> str:
        """
        Compute a hash representing the current state of the app map.
        """
        from app.utils.hash import compute_version_hash as _compute_version_hash
        content = f"{self.bundle_id}:{version_name or ''}:{update_time or ''}:{len(self.states)}:{len(self.transitions)}"
        return _compute_version_hash(content)

    def get_infrastructure_only(self) -> AtlasApp:
        """
        Return a copy with only infrastructure (static) elements.
        """
        filtered_states = {}
        for state_id, state in self.states.items():
            infra_elements = [e for e in state.elements if e.is_infrastructure]
            if infra_elements:
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
            transitions=[],
            menu_tree=self.menu_tree,
            version_hash=self.version_hash,
            explored_at=self.explored_at,
            exploration_depth=self.exploration_depth,
            is_dynamic=True,
        )

    def get_element_by_label(self, label: str) -> AtlasElement | None:
        """Search for an element by label across all states."""
        for state in self.states.values():
            if elem := state.get_element_by_label(label):
                return elem
        return None

    def add_state(self, state: AtlasState) -> None:
        """Add a new state to the app model."""
        self.states[state.state_id] = state

    def to_dict(self) -> dict:
        """Convert to dictionary with proper datetime handling."""
        data = self.model_dump()
        data["explored_at"] = self.explored_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> AtlasApp:
        """Create from dictionary."""
        return cls.model_validate(data)

    def to_json(self) -> str:
        """Export to JSON string."""
        return self.model_dump_json(indent=2)
