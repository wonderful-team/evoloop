import json
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.model_helpers import LegacyDictMixin
from app.utils.yaml import macro_from_yaml, macro_to_yaml, YAMLError


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
    NATIVE = "native"


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


class CollectMode(str, Enum):
    """Collect mode for LOOP steps - enables two-phase batch collection."""
    NORMAL = "normal"  # Standard loop execution
    LIST = "list"      # Phase 1: List collection - gather items without executing steps
    DETAIL = "detail"  # Phase 2: Detail execution - process collected items
    AUTO = "auto"      # Automatic: collect list first, then execute detail steps


class NavigationPayload(BaseModel, LegacyDictMixin):
    """Payload for navigation actions (goto, open_app)."""
    url: Optional[str] = None
    package_name: Optional[str] = Field(None, alias="package")
    app_name: Optional[str] = None
    wait_until: str = "load" # load | domcontentloaded | networkidle
    timeout_ms: int = 30000

    class Config:
        populate_by_name = True


class InteractionPayload(BaseModel, LegacyDictMixin):
    """Payload for UI interactions (click, input, scroll)."""
    # Coordinates (used if target_selector is missing or for vision correction)
    x: Optional[int] = None
    y: Optional[int] = None
    original_x: Optional[int] = None
    original_y: Optional[int] = None
    vision_corrected: bool = False
    
    # Text input
    text: Optional[str] = None
    append: bool = False
    enter: bool = True # Press enter after input
    
    # Mouse/Keyboard
    button: str = "left" # left | middle | right
    clicks: int = 1
    modifiers: List[str] = Field(default_factory=list) # shift | control | alt | meta
    
    # Scroll / Swipe
    direction: str = "down" # up | down | left | right
    amount: float = 0.5 # 0.0 to 1.0 or pixels
    duration_ms: int = 300
    
    # Timing
    delay_after_ms: int = 100
    timeout_ms: int = 10000


class ControlPayload(BaseModel, LegacyDictMixin):
    """Payload for control flow (loop, if)."""
    # Loop specific
    items_key: str = "items"
    max_iterations: Union[int, str] = 100
    max_retries: int = 3
    backoff_base: float = 2.0
    
    # Batch collection (Phase 6)
    state_file: Optional[str] = None
    list_config: Dict[str, Any] = Field(default_factory=dict)
    detail_config: Dict[str, Any] = Field(default_factory=dict)


class ExtractionPayload(BaseModel, LegacyDictMixin):
    """Payload for data extraction steps."""
    attribute: Optional[str] = None
    script: Optional[str] = Field(None, alias="expression")
    region: Optional[Dict[str, int]] = None # {"x": 0, "y": 0, "w": 100, "h": 100}
    wait_for_selector: Optional[str] = None
    timeout_ms: int = 5000
    
    # Loop detail collection
    data_capture: Dict[str, str] = Field(default_factory=dict)

    class Config:
        populate_by_name = True



# Unified Payload Type
MacroPayload = Union[
    NavigationPayload, 
    InteractionPayload, 
    ControlPayload, 
    ExtractionPayload, 
    Dict[str, Any]
]


class MacroCondition(BaseModel):
    type: str = "element_exists"
    target_selector: Optional[str] = None
    # For future expansion (e.g., text_matches, url_is)
    params: Dict[str, Any] = Field(default_factory=dict)


class MacroStep(BaseModel, LegacyDictMixin):
    step_number: Optional[int] = None
    type: MacroStepType
    description: Optional[str] = None
    source: MacroSource = MacroSource.DOM
    
    # Optional fields for specific types
    event_type: Optional[MacroActionType] = None
    target_selector: Optional[str] = None
    payload: MacroPayload = Field(default_factory=dict)
    
    # Control Flow (if/loop)
    condition: Optional[MacroCondition] = None
    then_steps: List["MacroStep"] = Field(default_factory=list)
    else_steps: List["MacroStep"] = Field(default_factory=list)
    steps: List["MacroStep"] = Field(default_factory=list)
    max_iterations: Union[int, str] = 100

    # Batch Collection Mode (for LOOP steps)
    # Enables two-phase collection: LIST (gather) -> DETAIL (execute)
    collect_mode: CollectMode = CollectMode.NORMAL

    @model_validator(mode='before')
    @classmethod
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

        # 3. Pull metadata from payload if missing at root (LLM compatibility)
        payload = values.get("payload")
        if isinstance(payload, dict):
            # Pull 'condition'
            if payload.get("condition") and not values.get("condition"):
                values["condition"] = payload.get("condition")

            # Pull 'max_iterations'
            if payload.get("max_iterations") and not values.get("max_iterations"):
                values["max_iterations"] = payload.get("max_iterations")

            # Pull 'steps' if it's buried in payload (some LLMs do this)
            if payload.get("steps") and not values.get("steps"):
                values["steps"] = payload.get("steps")

            # Pull 'collect_mode' for batch collection
            if payload.get("collect_mode"):
                values["collect_mode"] = payload.get("collect_mode")

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
    @classmethod
    def check_step_numbers(cls, values):
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

    @classmethod
    def from_yaml(cls, yaml_content: str) -> "MacroScript":
        """Parse macro from YAML string."""
        steps = macro_from_yaml(yaml_content)
        return cls(steps=steps)
    
    def to_yaml(self) -> str:
        """Export macro to YAML string."""
        steps_data = []
        for step in self.steps:
            if hasattr(step, 'model_dump'):
                steps_data.append(step.model_dump())
            elif hasattr(step, 'dict'):
                steps_data.append(step.dict())
            else:
                steps_data.append(dict(step))
        return macro_to_yaml(steps_data)
    
    @classmethod
    def parse(cls, content: str, format: str = "auto") -> "MacroScript":
        """
        Parse macro from string (auto-detect or specified format).
        
        Args:
            content: String content (JSON or YAML)
            format: "auto", "json", or "yaml"
            
        Raises:
            ValueError: If parsing fails
            YAMLError: If YAML parsing fails
        """
        if format == "auto":
            # Auto-detect based on first non-whitespace char
            stripped = content.strip()
            if stripped.startswith(("{", "[")):
                format = "json"
            else:
                format = "yaml"
        
        if format == "yaml":
            return cls.from_yaml(content)
        else:
            # JSON parsing
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    return cls(steps=data)
                elif isinstance(data, dict) and "steps" in data:
                    return cls(steps=data["steps"])
                else:
                    return cls(**data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")


# Resolve forward references (Pydantic V2)
MacroStep.model_rebuild()
