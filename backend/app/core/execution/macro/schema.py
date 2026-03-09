from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


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


class ExtractType(str, Enum):
    """Valid extract types for EXTRACT steps."""
    GET_TEXT = "get_text"
    GET_ATTRIBUTE = "get_attribute"
    GET_HTML = "get_html"
    GET_LINKS = "get_links"
    GET_ELEMENTS = "get_elements"  # Get multiple elements
    SCREENSHOT = "screenshot"
    GUI_EXTRACT = "gui_extract"  # Coordinate-based GUI extraction (OCR)
    DUMP_UI = "dump_ui"
    RUN_JS = "run_js"
    BATCH = "batch"  # Internal: batched extract operations


class MacroCondition(BaseModel):
    type: str = "element_exists"
    target_selector: Optional[str] = None
    # For future expansion (e.g., text_matches, url_is)
    params: Dict[str, Any] = Field(default_factory=dict)


class MacroStep(BaseModel):
    step_number: Optional[int] = None
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

    @model_validator(mode='before')
    def migrate_legacy_fields(self, values):
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
    extract_type: Optional[ExtractType] = None
    key: Optional[str] = "data"

    @model_validator(mode='after')
    def validate_extract_type(self):
        """Validate extract_type is valid when step type is 'extract'."""
        if self.type == MacroStepType.EXTRACT and self.extract_type is None:
            raise ValueError("extract_type is required when step type is 'extract'")
        return self

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

    @model_validator(mode='before')
    def check_step_numbers(self, values):
        """Validate step numbers are unique and sequential."""
        steps = values.get('steps', []) if isinstance(values, dict) else getattr(values, 'steps', [])
        if not steps:
            return values

        def collect_step_numbers(steps_list, parent_num=""):
            """Recursively collect all step numbers including nested."""
            numbers = []
            for i, step in enumerate(steps_list, 1):
                current_num = f"{parent_num}.{i}" if parent_num else str(i)
                if isinstance(step, dict):
                    step_num = step.get('step_number')
                else:
                    step_num = getattr(step, 'step_number', None)
                numbers.append((current_num, step_num))

                # Check nested steps
                if isinstance(step, dict):
                    then_steps = step.get('then_steps', []) or []
                    else_steps = step.get('else_steps', []) or []
                    loop_steps = step.get('steps', []) or []
                else:
                    then_steps = getattr(step, 'then_steps', []) or []
                    else_steps = getattr(step, 'else_steps', []) or []
                    loop_steps = getattr(step, 'steps', []) or []

                if then_steps:
                    numbers.extend(collect_step_numbers(then_steps, current_num))
                if else_steps:
                    numbers.extend(collect_step_numbers(else_steps, current_num))
                if loop_steps:
                    numbers.extend(collect_step_numbers(loop_steps, current_num))

            return numbers

        all_numbers = collect_step_numbers(steps)
        seen = set()
        for path, num in all_numbers:
            if num in seen:
                raise ValueError(f"Duplicate step number '{num}' found at path '{path}'")
            if num is not None:
                seen.add(num)

        return values


# Resolve forward references
MacroStep.update_forward_refs()
