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
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from app.utils.model_helpers import LegacyDictMixin


class Rect(BaseModel):

    """Represents a rectangular area in UI coordinates."""
    x: int
    y: int
    width: int
    height: int


class ElementMetadata(BaseModel, LegacyDictMixin):
    """Platform-specific metadata for a UI element."""
    # Common cross-platform attributes
    class_name: Optional[str] = Field(None, alias="class")
    resource_id: Optional[str] = None
    
    # Android specific
    package_name: Optional[str] = None
    content_desc: Optional[str] = None
    checkable: bool = False
    checked: bool = False
    scrollable: bool = False
    
    # MacOS specific
    ax_identifier: Optional[str] = None
    ax_role: Optional[str] = None
    ax_subrole: Optional[str] = None
    
    # Catch-all for additional attributes
    extra: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def capture_extra(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        
        # Identify known fields (including aliases)
        known_fields = {f.alias or name for name, f in cls.model_fields.items()}
        
        extra = values.get("extra", {})
        for k, v in list(values.items()):
            if k not in known_fields and k != "extra":
                extra[k] = values.pop(k)
        
        values["extra"] = extra
        return values

    class Config:
        populate_by_name = True


class AtlasElement(BaseModel, LegacyDictMixin):
    """
    A semantic anchor for a single interactive UI element.
    Platform-agnostic representation.
    """
    role: str = ""                   # e.g., "BUTTON", "INPUT", "AXButton"
    label: str = ""                  # e.g., "Save", "File"
    ax_path: str = ""                # Primary structural path/locator (Legacy/macOS specific)
    os_identifier: Optional[str] = None # Cross-platform OS identifier
    ocr_confidence: Optional[float] = None # Vision/OCR confidence score
    shortcut: Optional[str] = None
    visual_hash: Optional[str] = None
    bounds: Optional[Rect] = None
    is_enabled: bool = True
    parent_menu: Optional[str] = None

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


class AtlasState(BaseModel, LegacyDictMixin):
    """
    A snapshot of the application at a given UI state (a 'screen').
    """
    state_id: str
    window_title: str
    elements: List[AtlasElement] = Field(default_factory=list)
    screenshot_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_infrastructure_only: bool = False

    def get_element_by_label(self, label: str) -> Optional[AtlasElement]:
        label_lower = label.lower()
        return next((e for e in self.elements if e.label.lower() == label_lower), None)

    def get_element_by_path(self, ax_path: str) -> Optional[AtlasElement]:
        return next((e for e in self.elements if e.ax_path == ax_path), None)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> AtlasState:
        return cls.model_validate(data)


class AtlasTransition(BaseModel, LegacyDictMixin):
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


class AtlasApp(BaseModel):
    """
    The complete structural map of an application.
    """
    app_name: str
    bundle_id: str
    platform: str
    states: Dict[str, AtlasState] = Field(default_factory=dict)
    transitions: List[AtlasTransition] = Field(default_factory=list)
    menu_tree: Dict[str, Any] = Field(default_factory=dict)
    version_hash: str = ""
    explored_at: datetime = Field(default_factory=datetime.now)
    exploration_depth: int = 0
    is_dynamic: bool = False

    @property
    def all_elements(self) -> List[AtlasElement]:
        elements = []
        for state in self.states.values():
            elements.extend(state.elements)
        return elements

    @property
    def infrastructure_elements(self) -> List[AtlasElement]:
        return [e for e in self.all_elements if e.is_infrastructure]

    def get_element_by_path(self, ax_path: str) -> Optional[AtlasElement]:
        """Search for an element by path across all states."""
        for state in self.states.values():
            if elem := state.get_element_by_path(ax_path):
                return elem
        return None

    def get_state_elements(self, state_id: str) -> List[AtlasElement]:
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

    def get_infrastructure_only(self) -> "AtlasApp":
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

    def get_element_by_label(self, label: str) -> Optional[AtlasElement]:
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


