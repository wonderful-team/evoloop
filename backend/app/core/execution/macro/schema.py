from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator, root_validator


class MacroSource(str, Enum):
    DOM = "dom"
    MOBILE = "mobile"
    DESKTOP = "desktop"
    GLOBAL = "global"


class MacroStepType(str, Enum):
    ACTION = "action"
    EXTRACT = "extract"
    CONTROL = "control"
    DUMP = "dump"
    IF = "if"
    LOOP = "loop"


class MacroActionType(str, Enum):
    # Navigation
    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    RELOAD = "reload"
    
    # Interaction
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TAP = "tap" # Alias for click on mobile
    LONG_PRESS = "long_press"
    INPUT = "input"
    TYPE_TEXT = "type_text" # Legacy alias
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    SWIPE = "swipe"
    DRAG_DROP = "drag_drop"
    HOVER = "hover"
    WAIT = "wait"
    WAIT_FOR = "wait_for"
    
    # Browser / Web
    SELECT_OPTION = "select_option"
    NEW_TAB = "new_tab"
    SWITCH_TAB = "switch_tab"
    UPLOAD = "upload"
    RUN_JS = "run_js"
    DIALOG_HANDLE = "dialog_handle"
    
    # Extraction / Perception
    GET_TEXT = "get_text"
    GET_ATTRIBUTE = "get_attribute"
    GET_HTML = "get_html"
    GET_LINKS = "get_links"
    SCREENSHOT = "screenshot"
    DUMP_UI = "dump_ui"
    
    # OS / App
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    HOME = "home"
    BACK_KEY = "back_key"
    MOUSE_CLICK = "mouse_click"
    APPLESCRIPT = "applescript"
    GET_ACTIVE_APP = "get_active_app"
    GET_INFO = "get_info"
    
    # Advanced / Generic
    BATCH = "batch"
    
    # Automation Primitives
    DETECT_PAGINATION = "detect_pagination"
    SCROLL_TO_BOTTOM = "scroll_to_bottom"


class MacroCondition(BaseModel):
    type: str = "element_exists"
    target_selector: Optional[str] = None
    # For future expansion (e.g., text_matches, url_is)
    params: Dict[str, Any] = Field(default_factory=dict)


class MacroStep(BaseModel):
    step_number: int
    type: MacroStepType
    description: Optional[str] = None
    source: MacroSource = MacroSource.DOM
    
    # Optional fields for specific types
    event_type: Optional[MacroActionType] = None
    target_selector: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    
    # Control Flow (if/loop)
    condition: Optional[MacroCondition] = None
    then_steps: List["MacroStep"] = Field(default_factory=list)
    else_steps: List["MacroStep"] = Field(default_factory=list)
    steps: List["MacroStep"] = Field(default_factory=list)
    max_iterations: int = 100

    @root_validator(pre=True)
    def migrate_legacy_fields(cls, values):
        # 1. Migrate Type
        step_type = values.get("type")
        if step_type in ("while", "batch_loop"):
            values["type"] = "loop"
        
        # 2. Migrate Steps (then/else/do/do_steps -> standardized field names)
        # Handle 'then' -> 'then_steps'
        if values.get("then") and not values.get("then_steps"):
            values["then_steps"] = values.pop("then")
            
        # Handle 'else' -> 'else_steps'
        if values.get("else") and not values.get("else_steps"):
            values["else_steps"] = values.pop("else")

        # Handle 'do' / 'do_steps' -> 'steps'
        legacy_steps = values.get("do") or values.get("do_steps")
        if legacy_steps and not values.get("steps"):
            values["steps"] = legacy_steps
            # Cleanup legacy keys from the dict to avoid pollution if needed, 
            # but usually pydantic ignores extra fields anyway.
            
        return values
    
    # Extraction
    extract_type: Optional[str] = None
    key: Optional[str] = "data"

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True


class MacroMetadata(BaseModel):
    version: str = "1.0"
    created_at: Optional[float] = None
    author: Optional[str] = "system"
    thread_id: Optional[str] = None


class MacroScript(BaseModel):
    metadata: MacroMetadata = Field(default_factory=MacroMetadata)
    steps: List[MacroStep] = Field(default_factory=list)
    parameters_schema: List[Dict[str, Any]] = Field(default_factory=list)


# Resolve forward references
MacroStep.update_forward_refs()
