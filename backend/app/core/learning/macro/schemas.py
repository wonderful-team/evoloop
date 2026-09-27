"""Schemas for macro module."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.learning import constants as _mc

# re-export：公共 API（测试与外部以 schemas 为单一导入源，勿删）
from app.core.learning.constants import (  # noqa: F401
    DEFAULT_ALLOWED_FAMILIES,
    RISK_TIER_ORDER,
    RISK_TIERS,
)
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.yaml import macro_from_yaml, macro_to_yaml

# === Classes migrated from schema.py (singular) ===


class MacroSource(str, Enum):
    DOM = _mc.DOM
    MOBILE = _mc.MOBILE
    DESKTOP = _mc.DESKTOP
    GLOBAL = _mc.GLOBAL


class MacroStepType(str, Enum):
    ACTION = _mc.ACTION
    EXTRACT = _mc.EXTRACT
    CONTROL = _mc.CONTROL
    DUMP = _mc.DUMP
    IF = _mc.IF
    LOOP = _mc.LOOP
    NATIVE = _mc.NATIVE
    BASH = _mc.BASH


class MacroActionType(str, Enum):
    # Navigation
    NAVIGATE = _mc.NAVIGATE
    BACK = _mc.BACK
    FORWARD = _mc.FORWARD
    RELOAD = _mc.RELOAD
    FRONTEND_NAVIGATE = _mc.FRONTEND_NAVIGATE

    # Interaction
    CLICK = _mc.CLICK
    DOUBLE_CLICK = _mc.DOUBLE_CLICK
    TAP = _mc.TAP  # Alias for click on mobile
    LONG_PRESS = _mc.LONG_PRESS
    INPUT = _mc.INPUT
    TYPE_TEXT = _mc.TYPE_TEXT  # Legacy alias
    KEY_PRESS = _mc.KEY_PRESS
    SCROLL = _mc.SCROLL
    SWIPE = _mc.SWIPE
    DRAG_DROP = _mc.DRAG_DROP
    HOVER = _mc.HOVER
    WAIT = _mc.WAIT
    WAIT_FOR = _mc.WAIT_FOR

    # Browser / Web
    SELECT_OPTION = _mc.SELECT_OPTION
    NEW_TAB = _mc.NEW_TAB
    SWITCH_TAB = _mc.SWITCH_TAB
    UPLOAD = _mc.UPLOAD
    RUN_JS = _mc.RUN_JS
    DIALOG_HANDLE = _mc.DIALOG_HANDLE

    # Extraction / Perception
    GET_TEXT = _mc.GET_TEXT
    GET_ATTRIBUTE = _mc.GET_ATTRIBUTE
    GET_HTML = _mc.GET_HTML
    GET_LINKS = _mc.GET_LINKS
    SCREENSHOT = _mc.SCREENSHOT
    DUMP_UI = _mc.DUMP_UI

    # Code execution / system-level escape hatches
    APPLESCRIPT = _mc.APPLESCRIPT
    BASH = _mc.BASH
    EVALUATE = _mc.EVALUATE

    # OS / App
    OPEN_APP = _mc.OPEN_APP
    CLOSE_APP = _mc.CLOSE_APP
    HOME = _mc.HOME
    BACK_KEY = _mc.BACK_KEY
    MOUSE_CLICK = _mc.MOUSE_CLICK
    GET_ACTIVE_APP = _mc.GET_ACTIVE_APP
    GET_INFO = _mc.GET_INFO
    NOOP = _mc.NOOP

    # Atlas-Native AX primitives (macOS, focus-free)
    AX_PRESS = _mc.AX_PRESS
    AX_MENU_PRESS = _mc.AX_MENU_PRESS
    AX_SET_VALUE = _mc.AX_SET_VALUE

    # Advanced / Generic
    BATCH = _mc.BATCH

    # Automation Primitives
    DETECT_PAGINATION = _mc.DETECT_PAGINATION
    SCROLL_TO_BOTTOM = _mc.SCROLL_TO_BOTTOM

    # CGEvent click (bypasses AX/OCR, uses Quartz directly)
    CGCLICK = _mc.CGCLICK


def action_family(step_type: MacroStepType, event_type: MacroActionType | str | None) -> str:
    """Derive action family from a macro step using priority:
    1. escape  — type==NATIVE or type==BASH (system-level execution)
    2. observe — type in (EXTRACT, DUMP), including run_js extraction
    3. control — type in (CONTROL, IF, LOOP)
    4. escape  — event_type in (applescript, run_js, bash) when used as actions
    5. act     — everything else

    Note: run_js inside an EXTRACT step is treated as observation/data extraction,
    not as arbitrary code execution, because its purpose is to read page state.
    run_js as an ACTION step remains escape.
    """
    if step_type in (MacroStepType.NATIVE, MacroStepType.BASH):
        return "escape"
    if step_type in (MacroStepType.EXTRACT, MacroStepType.DUMP):
        return "observe"
    if step_type in (MacroStepType.CONTROL, MacroStepType.IF, MacroStepType.LOOP):
        return "control"
    if event_type and str(event_type) in (_mc.APPLESCRIPT, _mc.RUN_JS, _mc.BASH):
        return "escape"
    return "act"


def action_risk(event_type: MacroActionType | str | None) -> str:
    """Default risk tier for a given action type."""
    _risk: dict[str, str] = {
        # Navigation — observe
        _mc.NAVIGATE: "observe",
        _mc.BACK: "observe",
        _mc.FORWARD: "observe",
        _mc.RELOAD: "observe",
        # Interaction — act (safe clicks / scrolls)
        _mc.CLICK: "act",
        _mc.DOUBLE_CLICK: "act",
        _mc.TAP: "act",
        _mc.LONG_PRESS: "act",
        _mc.KEY_PRESS: "act",
        _mc.SCROLL: "observe",
        _mc.SWIPE: "act",
        _mc.DRAG_DROP: "act",
        _mc.HOVER: "act",
        _mc.WAIT: "observe",
        _mc.WAIT_FOR: "observe",
        # Data input — data
        _mc.INPUT: "data",
        _mc.TYPE_TEXT: "data",
        _mc.SELECT_OPTION: "data",
        _mc.UPLOAD: "data",
        # Browser tabs — act
        _mc.NEW_TAB: "act",
        _mc.SWITCH_TAB: "act",
        _mc.DIALOG_HANDLE: "act",
        # Code execution — escape
        _mc.RUN_JS: "escape",
        _mc.APPLESCRIPT: "escape",
        _mc.BASH: "escape",
        # Perception / read-only — observe
        _mc.GET_TEXT: "observe",
        _mc.GET_ATTRIBUTE: "observe",
        _mc.GET_HTML: "observe",
        _mc.GET_LINKS: "observe",
        _mc.SCREENSHOT: "observe",
        _mc.DUMP_UI: "observe",
        _mc.GET_ELEMENTS: "observe",
        _mc.GUI_EXTRACT: "observe",
        # Desktop app — act
        _mc.OPEN_APP: "act",
        _mc.CLOSE_APP: "act",
        _mc.HOME: "act",
        _mc.BACK_KEY: "act",
        _mc.MOUSE_CLICK: "act",
        _mc.GET_ACTIVE_APP: "observe",
        _mc.GET_INFO: "observe",
        # Atlas-Native AX primitives — act / data
        _mc.AX_PRESS: "act",
        _mc.AX_MENU_PRESS: "act",
        _mc.AX_SET_VALUE: "data",
        # Advanced
        _mc.BATCH: "observe",
        _mc.DETECT_PAGINATION: "observe",
        _mc.SCROLL_TO_BOTTOM: "observe",
        _mc.EVALUATE: "escape",
    }
    if event_type is None:
        return "observe"
    return _risk.get(str(event_type), "act")


def _step_nested(step: Any) -> tuple[list[Any], list[Any], list[Any]]:
    """Return (then_steps, else_steps, steps) from a MacroStep or dict."""
    if isinstance(step, dict):
        return (
            step.get("then_steps") or [],
            step.get("else_steps") or [],
            step.get("steps") or [],
        )
    return (
        getattr(step, "then_steps", None) or [],
        getattr(step, "else_steps", None) or [],
        getattr(step, "steps", None) or [],
    )


def iter_macro_steps(steps: list[Any]):
    """Depth-first walk over a macro step tree (MacroStep or dict).

    Yields (family, step_type, event_type) for every step, including nested
    then/else/steps bodies. Shared by risk/family scanners so the tree-walk
    logic lives in one place instead of being copied across callers.
    """
    for step in steps:
        if isinstance(step, dict):
            step_type = step.get("type")
            event_type = step.get("event_type")
        else:
            step_type = getattr(step, "type", None)
            event_type = getattr(step, "event_type", None)
        family = action_family(step_type, event_type)
        yield family, step_type, event_type
        then_steps, else_steps, body = _step_nested(step)
        for nested in (then_steps, else_steps, body):
            yield from iter_macro_steps(nested)


def scan_step_families(steps: list[Any], allowed: set[str]) -> str | None:
    """Reject any step whose action family is not in the allowed set.

    Accepts a list of MacroStep objects or dicts. Returns the first rejection
    reason, or None when every step (including nested) is allowed.
    """
    for family, step_type, event_type in iter_macro_steps(steps):
        if family not in allowed:
            return (
                f"step type={step_type} event_type={event_type} "
                f"is in disallowed family '{family}'"
            )
    return None


def compute_max_risk(steps: list[Any]) -> str:
    """Return the highest risk tier present in the script.

    Family-aware: steps in the "observe" family (EXTRACT / DUMP step types,
    including run_js used inside them for reading page state) contribute at
    most "data" risk — matching scan_step_families, which classifies those
    steps as observation rather than code execution. run_js/applescript/bash
    as ACTION steps still yield "escape".
    """
    max_risk = "observe"
    for family, _step_type, event_type in iter_macro_steps(steps):
        if family == "observe":
            risk = "data" if event_type == _mc.RUN_JS else "observe"
        else:
            risk = action_risk(event_type)
        if RISK_TIER_ORDER.get(risk, 0) > RISK_TIER_ORDER.get(max_risk, 0):
            max_risk = risk
    return max_risk


class ExtractType(str, Enum):
    """Valid extract types for EXTRACT steps."""

    GET_TEXT = _mc.GET_TEXT
    GET_ATTRIBUTE = _mc.GET_ATTRIBUTE
    GET_HTML = _mc.GET_HTML
    GET_LINKS = _mc.GET_LINKS
    GET_ELEMENTS = _mc.GET_ELEMENTS  # Get multiple elements
    SCREENSHOT = _mc.SCREENSHOT
    GUI_EXTRACT = _mc.GUI_EXTRACT  # Coordinate-based GUI extraction (OCR)
    DUMP_UI = _mc.DUMP_UI
    RUN_JS = _mc.RUN_JS
    BATCH = _mc.BATCH  # Internal: batched extract operations


class CollectMode(str, Enum):
    """Collect mode for LOOP steps - enables two-phase batch collection."""

    NORMAL = "normal"  # Standard loop execution
    LIST = "list"  # Phase 1: List collection - gather items without executing steps
    DETAIL = "detail"  # Phase 2: Detail execution - process collected items
    AUTO = "auto"  # Automatic: collect list first, then execute detail steps


# Unified Payload Type
# Plain dict so step payloads keep exactly the keys the author wrote — the
# engine owns its own defaults (timeout_ms etc.) instead of silently inheriting
# model defaults from a Pydantic union.
MacroPayload = dict[str, Any]


class MacroCondition(DynamicBaseModel):
    type: str = "element_exists"
    target_selector: str | None = None
    # For future expansion (e.g., text_matches, url_is)
    params: dict[str, Any] = Field(default_factory=dict)


class MacroStep(DynamicBaseModel):
    step_number: int | None = None
    type: MacroStepType
    description: str | None = None
    source: MacroSource = MacroSource.DOM

    # Optional fields for specific types
    event_type: MacroActionType | None = None
    target_selector: str | None = None
    payload: MacroPayload = Field(default_factory=dict)

    # Control Flow (if/loop)
    condition: MacroCondition | None = None
    then_steps: list[MacroStep] = Field(default_factory=list)
    else_steps: list[MacroStep] = Field(default_factory=list)
    steps: list[MacroStep] = Field(default_factory=list)
    max_iterations: int | str = 100

    # Batch Collection Mode (for LOOP steps)
    # Enables two-phase collection: LIST (gather) -> DETAIL (execute)
    collect_mode: CollectMode = CollectMode.NORMAL

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, values):
        # 1. Migrate Type
        step_type = values.get("type")
        if step_type in (_mc.WHILE, _mc.BATCH_LOOP):
            values["type"] = _mc.LOOP

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
    extract_type: ExtractType | None = None
    key: str | None = "data"

    @model_validator(mode="after")
    def validate_extract_type(self):
        """Validate extract_type is valid when step type is 'extract'."""
        if self.type == MacroStepType.EXTRACT and self.extract_type is None:
            raise ValueError("extract_type is required when step type is 'extract'")
        return self

    model_config = ConfigDict(
        extra="allow",
        use_enum_values=True,
        populate_by_name=True,
    )


class MacroMetadata(BaseModel):
    version: str = "1.0"
    created_at: float | None = None
    author: str | None = "system"
    thread_id: str | None = None


class MacroScript(DynamicBaseModel):
    metadata: MacroMetadata = Field(default_factory=MacroMetadata)
    steps: list[MacroStep] = Field(default_factory=list)
    parameters_schema: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def check_step_numbers(cls, values):
        """Validate step numbers are unique and sequential."""
        steps = (
            values.get("steps", [])
            if isinstance(values, dict)
            else getattr(values, "steps", [])
        )
        if not steps:
            return values

        def collect_step_numbers(steps_list, parent_num=""):
            """Recursively collect all step numbers including nested."""
            numbers = []
            for i, step in enumerate(steps_list, 1):
                current_num = f"{parent_num}.{i}" if parent_num else str(i)
                if isinstance(step, dict):
                    step_num = step.get("step_number")
                else:
                    step_num = getattr(step, "step_number", None)
                numbers.append((current_num, step_num))

                # Check nested steps
                if isinstance(step, dict):
                    then_steps = step.get("then_steps", []) or []
                    else_steps = step.get("else_steps", []) or []
                    loop_steps = step.get("steps", []) or []
                else:
                    then_steps = getattr(step, "then_steps", []) or []
                    else_steps = getattr(step, "else_steps", []) or []
                    loop_steps = getattr(step, "steps", []) or []

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
                raise ValueError(
                    f"Duplicate step number '{num}' found at path '{path}'"
                )
            if num is not None:
                seen.add(num)

        return values

    @classmethod
    def from_yaml(cls, yaml_content: str) -> MacroScript:
        """Parse macro from YAML string."""
        steps = macro_from_yaml(yaml_content)
        return cls(steps=steps)

    def to_yaml(self) -> str:
        """Export macro to YAML string."""
        steps_data = []
        for step in self.steps:
            if hasattr(step, "model_dump"):
                steps_data.append(step.model_dump(mode="json"))
            elif hasattr(step, "dict"):
                steps_data.append(step.model_dump())
            else:
                steps_data.append(dict(step))
        return macro_to_yaml(steps_data)

    @classmethod
    def parse(cls, content: str, format: str = "auto") -> MacroScript:
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

# === Original schemas.py classes ===


class HealingDecision(DynamicBaseModel):
    """Result of a self-healing policy check."""

    allowed: bool
    reason: str
    # Source of the decision for debugging
    source: str  # "global" | "macro" | "execution" | "allowed"


class MacroRunResult(DynamicBaseModel):
    success: bool
    message: str
    extracted_data: dict[str, Any] | None = None
    allow_self_healing: bool | None = None
    healing_disabled_reason: str | None = None
    healing_disabled_source: str | None = None
    suggestions: list[str] | None = None
    status: str | None = None  # e.g. "fallback_required"
    fallback_context: dict[str, Any] | None = None
    step_log: list[dict[str, Any]] | None = None  # per-step execution records
    execution_warnings: list[str] | None = (
        None  # non-fatal signals (e.g. zero-iteration loop)
    )


class MacroVerificationResult(DynamicBaseModel):
    """Result of a macro script's real-execution verification run."""

    status: str
    success: bool
    missing_keys: list[str] = []
    extracted_count: int = 0
    error: str | None = None
    step_log: list[dict[str, Any]] | None = None  # per-step execution records
