from __future__ import annotations

from dataclasses import dataclass

from app.core.learning.schemas import ActionCategory


@dataclass(frozen=True)
class ExecutionPolicy:
    """Policy knobs that differ between macro transports (web vs voice)."""

    allow_self_heal: bool
    allowed_sources: frozenset[str] | None = None  # None = unrestricted
    allowed_families: frozenset[str] | None = None  # None = unrestricted
    max_risk_tier: str | None = None  # None = unrestricted


# Mapping of generic event types to high-level categories
EVENT_CATEGORY_MAP = {
    "tool_call": ActionCategory.QUERY,  # Default, refined by tool-specific map
    "click": ActionCategory.INTERACTION,
    "input": ActionCategory.INTERACTION,
    "node_start": ActionCategory.OTHER,
    "llm_output": ActionCategory.DECISION,
}

# Tool-specific category overrides
TOOL_CATEGORY_MAP = {
    "read": ActionCategory.QUERY,
    "write": ActionCategory.EDIT,
    "edit": ActionCategory.EDIT,
    "grep": ActionCategory.QUERY,
    "glob": ActionCategory.QUERY,
    "list_dir": ActionCategory.QUERY,
    "websearch": ActionCategory.QUERY,
    "bash": ActionCategory.COMMAND,
    "mobile": ActionCategory.SYSTEM_INTERACTION,
    "desktop": ActionCategory.SYSTEM_INTERACTION,
}

# Multimodal synthesis defaults
DEFAULT_VIDEO_FPS = 15

# Workflow synthesis modes
SKILL = "skill"
MACRO = "macro"

# Skill folder anatomy
REQUIRED_FILES = ["SKILL.md"]
RECOMMENDED_DIRS = ["scripts", "references", "assets"]

# LearnedSkill statuses trusted for auto-routing
ROUTABLE_STATUSES = frozenset({"verified"})

# ---- Sources ----
DOM = "dom"
MOBILE = "mobile"
DESKTOP = "desktop"
GLOBAL = "global"

# ---- Step types ----
ACTION = "action"
EXTRACT = "extract"
CONTROL = "control"
DUMP = "dump"
IF = "if"
LOOP = "loop"
NATIVE = "native"
BASH = "bash"

# Legacy step type aliases normalized during cleanup / validation
WHILE = "while"
BATCH_LOOP = "batch_loop"

# ---- Action types ----
NAVIGATE = "navigate"
BACK = "back"
FORWARD = "forward"
RELOAD = "reload"
FRONTEND_NAVIGATE = "frontend_navigate"

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

SELECT_OPTION = "select_option"
NEW_TAB = "new_tab"
SWITCH_TAB = "switch_tab"
UPLOAD = "upload"
RUN_JS = "run_js"
DIALOG_HANDLE = "dialog_handle"

GET_TEXT = "get_text"
GET_ATTRIBUTE = "get_attribute"
GET_HTML = "get_html"
GET_LINKS = "get_links"
GET_ELEMENTS = "get_elements"
SCREENSHOT = "screenshot"
DUMP_UI = "dump_ui"
GUI_EXTRACT = "gui_extract"

APPLESCRIPT = "applescript"
EVALUATE = "evaluate"

OPEN_APP = "open_app"
CLOSE_APP = "close_app"
HOME = "home"
BACK_KEY = "back_key"
MOUSE_CLICK = "mouse_click"
GET_ACTIVE_APP = "get_active_app"
GET_INFO = "get_info"
NOOP = "noop"

AX_PRESS = "ax_press"
AX_MENU_PRESS = "ax_menu_press"
AX_SET_VALUE = "ax_set_value"

DETECT_PAGINATION = "detect_pagination"
SCROLL_TO_BOTTOM = "scroll_to_bottom"
CGCLICK = "cgclick"
BATCH = "batch"

# ---- Raw trace event types normalized into macro actions ----
TOUCH_DOWN = "touch_down"
TOUCH_UP = "touch_up"
KEY = "key"

# ---- Intermediate / legacy trace action names ----
GOTO = "goto"
INPUT_TEXT = "input_text"

# ---- Native macro maintenance ----
MAX_MACROS_PER_APP = 500

# ---- UI action whitelist (compiler + creator eligibility) ----
ALLOWED_UI_ACTIONS: frozenset[str] = frozenset(
    {
        GOTO,
        NAVIGATE,
        CLICK,
        TYPE_TEXT,
        INPUT,
        KEY_PRESS,
        SCROLL,
        WAIT,
        WAIT_FOR,
        EXTRACT,
        GET_TEXT,
        GET_HTML,
        GET_ATTRIBUTE,
        RUN_JS,
        EVALUATE,
        TAP,
        LONG_PRESS,
        SWIPE,
        INPUT_TEXT,
        OPEN_APP,
        BACK,
        HOME,
        APPLESCRIPT,
        DRAG_DROP,
        DETECT_PAGINATION,
        SCROLL_TO_BOTTOM,
        SCREENSHOT,
        DUMP,
        DUMP_UI,
    }
)

# ---- Default execution policies ----
WEB_POLICY = ExecutionPolicy(allow_self_heal=True)
# Voice policy: fast-fail, no agentic self-healing.  allowed_sources only gates
# UI-bound steps; utility/control steps remain headless-safe.
VOICE_POLICY = ExecutionPolicy(
    allow_self_heal=False,
    allowed_sources=frozenset({DESKTOP, DOM}),
)

# ---- MacroRunResult.status (execution outcome) ----
RUN_RESULT_FALLBACK_REQUIRED = "fallback_required"
RUN_RESULT_CANCELLED = "cancelled"

# ---- Macro loop item lifecycle (collect_loop item["status"]) ----
LOOP_ITEM_PENDING = "pending"
LOOP_ITEM_DONE = "done"
LOOP_ITEM_FAILED = "failed"

# ---- Macro collect_loop phase (state["phase"]) ----
LOOP_PHASE_LIST = "list"
LOOP_PHASE_DETAIL = "detail"
LOOP_PHASE_COMPLETED = "completed"

# ---- Macro verification result status (MacroVerificationResult.status) ----
VERIFY_STATUS_SUCCESS = "success"
VERIFY_STATUS_FAILED = "failed"
VERIFY_STATUS_ERROR = "error"

# ---- Macro Creation Eligibility ----
# Event types excluded from macro creation (LLM internals, queries, memory ops)
EXCLUDED_EVENT_TYPES = frozenset(
    {
        "llm_output",
        "tool_result",
        "node_start",
        "macro_thought",
        "list_macros",
        "list_skills",
        "search_history",
        "recall",
        "read",
        "list_dir",
        "grep",
        "glob",
        "question",
    }
)

# Raw mobile mirror events normalized into macro actions
RAW_MOBILE_EVENT_TYPES = frozenset(
    {
        TOUCH_DOWN,
        TOUCH_UP,
        MOUSE_CLICK,
        SWIPE,
        KEY,
    }
)

# ---- Action Family & Risk Model (migrated from macro/schemas.py) ----
# Risk tiers ordered from lowest to highest
RISK_TIERS: list[str] = ["observe", "act", "data", "money", "escape"]
RISK_TIER_ORDER: dict[str, int] = {t: i for i, t in enumerate(RISK_TIERS)}

# Families allowed for Agent-authored macro scripts
# escape (bash/native/applescript) temporarily allowed for local JSON data processing
DEFAULT_ALLOWED_FAMILIES: set[str] = {"observe", "act", "control", "data", "escape"}
