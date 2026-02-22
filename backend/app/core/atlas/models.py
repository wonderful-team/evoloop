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
from typing import Any, List, Dict, Optional


@dataclass
class AtlasElement:
    """
    A semantic anchor for a single interactive UI element.
    Platform-agnostic representation.
    """
    role: str                        # e.g., "BUTTON", "INPUT", "AXButton"
    label: str                       # e.g., "Save", "File"
    ax_path: str                     # Primary structural path/locator
    shortcut: Optional[str] = None      
    visual_hash: Optional[str] = None   
    bounds: Optional[Dict[str, int]] = None       
    is_enabled: bool = True
    parent_menu: Optional[str] = None   

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
    def from_dict(cls, data: dict) -> "AtlasElement":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AtlasState:
    """
    A snapshot of the application at a given UI state (a 'screen').
    """
    state_id: str                           
    window_title: str                       
    elements: List[AtlasElement] = field(default_factory=list)
    screenshot_hash: Optional[str] = None      
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_element_by_label(self, label: str) -> Optional[AtlasElement]:
        label_lower = label.lower()
        return next((e for e in self.elements if e.label.lower() == label_lower), None)

    def get_element_by_path(self, ax_path: str) -> Optional[AtlasElement]:
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
    def from_dict(cls, data: dict) -> "AtlasState":
        elements = [AtlasElement.from_dict(e) for e in data.get("elements", [])]
        return cls(
            state_id=data["state_id"],
            window_title=data["window_title"],
            elements=elements,
            screenshot_hash=data.get("screenshot_hash"),
            metadata=data.get("metadata", {}),
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
    def from_dict(cls, data: dict) -> "AtlasTransition":
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
    """
    app_name: str                                           
    bundle_id: str                                          
    platform: str                                           
    states: Dict[str, AtlasState] = field(default_factory=dict)
    transitions: List[AtlasTransition] = field(default_factory=list)
    menu_tree: Dict[str, Any] = field(default_factory=dict)   
    version_hash: str = ""                                  
    explored_at: datetime = field(default_factory=datetime.now)
    exploration_depth: int = 0                              

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

    def get_all_elements(self) -> List[AtlasElement]:
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
    def from_dict(cls, data: dict) -> "AtlasApp":
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
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AtlasApp":
        return cls.from_dict(json.loads(json_str))
