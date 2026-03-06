from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator


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
    # Legacy support
    IF = "if"
    WHILE = "while"


class MacroActionType(str, Enum):
    # Navigation (Cross-platform)
    GOTO = "goto"
    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    RELOAD = "reload"
    GET_URL = "get_url"
    
    # Common Interaction
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TAP = "tap"
    LONG_PRESS = "long_press"
    INPUT = "input"
    TYPE_TEXT = "type_text"
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    SWIPE = "swipe"
    DRAG_DROP = "drag_drop"
    HOVER = "hover"
    WAIT = "wait"
    WAIT_FOR = "wait_for"
    
    # Browser / Web Specific
    SELECT_OPTION = "select_option"
    NEW_TAB = "new_tab"
    SWITCH_TAB = "switch_tab"
    UPLOAD = "upload"
    RUN_JS = "run_js"
    EVALUATE = "evaluate"
    GET_COOKIES = "get_cookies"
    SET_COOKIES = "set_cookies"
    LOCAL_STORAGE = "local_storage"
    NETWORK_WAIT = "network_wait"
    DIALOG_HANDLE = "dialog_handle"
    
    # OS / App Level (Mobile & Desktop)
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    BACK_KEY = "back_key" # Mobile physical back
    HOME = "home"
    APPLESCRIPT = "applescript"
    SCREENSHOT = "screenshot"
    DUMP_UI = "dump_ui"
    
    # Advanced
    BATCH = "batch"


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
    
    # Control Flow (if/while)
    condition: Optional[MacroCondition] = None
    then_steps: List["MacroStep"] = Field(default_factory=list, alias="then")
    else_steps: List["MacroStep"] = Field(default_factory=list, alias="else")
    do_steps: List["MacroStep"] = Field(default_factory=list, alias="do")
    max_iterations: int = 100
    
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
