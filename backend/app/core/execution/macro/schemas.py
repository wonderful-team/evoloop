"""Schemas for macro module."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.yaml import macro_from_yaml, macro_to_yaml

# === Classes migrated from schema.py (singular) ===


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
    BASH = "bash"


class MacroActionType(str, Enum):
    # Navigation
    NAVIGATE = "navigate"
    BACK = "back"
    FORWARD = "forward"
    RELOAD = "reload"
    FRONTEND_NAVIGATE = "frontend_navigate"

    # Interaction
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    TAP = "tap"  # Alias for click on mobile
    LONG_PRESS = "long_press"
    INPUT = "input"
    TYPE_TEXT = "type_text"  # Legacy alias
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

    # Code execution / system-level escape hatches
    APPLESCRIPT = "applescript"
    BASH = "bash"
    EVALUATE = "evaluate"

    # OS / App
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    HOME = "home"
    BACK_KEY = "back_key"
    MOUSE_CLICK = "mouse_click"
    GET_ACTIVE_APP = "get_active_app"
    GET_INFO = "get_info"
    NOOP = "noop"

    # Atlas-Native AX primitives (macOS, focus-free)
    AX_PRESS = "ax_press"
    AX_MENU_PRESS = "ax_menu_press"
    AX_SET_VALUE = "ax_set_value"

    # Advanced / Generic
    BATCH = "batch"

    # Automation Primitives
    DETECT_PAGINATION = "detect_pagination"
    SCROLL_TO_BOTTOM = "scroll_to_bottom"

    # CGEvent click (bypasses AX/OCR, uses Quartz directly)
    CGCLICK = "cgclick"


# ---- P0: Action Family & Risk Model (§7.2, §10.1) ----

# Risk tiers ordered from lowest to highest.
RISK_TIERS: list[str] = ["observe", "act", "data", "money", "escape"]
RISK_TIER_ORDER: dict[str, int] = {t: i for i, t in enumerate(RISK_TIERS)}


def action_family(step_type: MacroStepType, event_type: MacroActionType | str | None) -> str:
    """Derive action family from a macro step using priority:
    1. escape  — type==NATIVE or event_type in (APPLESCRIPT, RUN_JS)
    2. observe — type in (EXTRACT, DUMP) or perception event_type
    3. control — type in (CONTROL, IF, LOOP)
    4. act     — everything else
    """
    if step_type in (MacroStepType.NATIVE, MacroStepType.BASH):
        return "escape"
    if event_type and str(event_type) in ("applescript", "run_js", "bash"):
        return "escape"
    if step_type in (MacroStepType.EXTRACT, MacroStepType.DUMP):
        return "observe"
    _perception = frozenset({
        "get_text",
        "get_attribute",
        "get_html",
        "get_links",
        "get_elements",
        "screenshot",
        "dump_ui",
        "gui_extract",
    })
    if event_type and str(event_type) in _perception:
        return "observe"
    if step_type in (MacroStepType.CONTROL, MacroStepType.IF, MacroStepType.LOOP):
        return "control"
    return "act"


def action_risk(event_type: MacroActionType | str | None) -> str:
    """Default risk tier for a given action type."""
    _risk: dict[str, str] = {
        # Navigation — observe
        "navigate": "observe",
        "back": "observe",
        "forward": "observe",
        "reload": "observe",
        # Interaction — act (safe clicks / scrolls)
        "click": "act",
        "double_click": "act",
        "tap": "act",
        "long_press": "act",
        "key_press": "act",
        "scroll": "observe",
        "swipe": "act",
        "drag_drop": "act",
        "hover": "act",
        "wait": "observe",
        "wait_for": "observe",
        # Data input — data
        "input": "data",
        "type_text": "data",
        "select_option": "data",
        "upload": "data",
        # Browser tabs — act
        "new_tab": "act",
        "switch_tab": "act",
        "dialog_handle": "act",
        # Code execution — escape
        "run_js": "escape",
        "applescript": "escape",
        "bash": "escape",
        # Perception / read-only — observe
        "get_text": "observe",
        "get_attribute": "observe",
        "get_html": "observe",
        "get_links": "observe",
        "screenshot": "observe",
        "dump_ui": "observe",
        "get_elements": "observe",
        "gui_extract": "observe",
        # Desktop app — act
        "open_app": "act",
        "close_app": "act",
        "home": "act",
        "back_key": "act",
        "mouse_click": "act",
        "get_active_app": "observe",
        "get_info": "observe",
        # Atlas-Native AX primitives — act / data
        "ax_press": "act",
        "ax_menu_press": "act",
        "ax_set_value": "data",
        # Advanced
        "batch": "observe",
        "detect_pagination": "observe",
        "scroll_to_bottom": "observe",
        "evaluate": "escape",
    }
    if event_type is None:
        return "observe"
    return _risk.get(str(event_type), "act")


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
    LIST = "list"  # Phase 1: List collection - gather items without executing steps
    DETAIL = "detail"  # Phase 2: Detail execution - process collected items
    AUTO = "auto"  # Automatic: collect list first, then execute detail steps


class NavigationPayload(DynamicBaseModel):
    """Payload for navigation actions (goto, open_app)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    url: str | None = None
    package_name: str | None = Field(None, alias="package")
    app_name: str | None = None
    wait_until: str = "load"  # load | domcontentloaded | networkidle
    timeout_ms: int = 30000


class InteractionPayload(DynamicBaseModel):
    """Payload for UI interactions (click, input, scroll)."""

    # Coordinates (used if target_selector is missing or for vision correction)
    x: int | None = None
    y: int | None = None
    original_x: int | None = None
    original_y: int | None = None
    vision_corrected: bool = False

    # Text input
    text: str | None = None
    append: bool = False
    enter: bool = True  # Press enter after input

    # Mouse/Keyboard
    button: str = "left"  # left | middle | right
    clicks: int = 1
    modifiers: list[str] = Field(default_factory=list)  # shift | control | alt | meta

    # Scroll / Swipe
    direction: str = "down"  # up | down | left | right
    amount: float = 0.5  # 0.0 to 1.0 or pixels
    duration_ms: int = 300

    # Timing
    delay_after_ms: int = 100
    timeout_ms: int = 10000


class ControlPayload(DynamicBaseModel):
    """Payload for control flow (loop, if)."""

    # Loop specific
    items_key: str = "items"
    max_iterations: int | str = 100
    max_retries: int = 3
    backoff_base: float = 2.0

    # Batch collection (Phase 6)
    state_file: str | None = None
    list_config: dict[str, Any] = Field(default_factory=dict)
    detail_config: dict[str, Any] = Field(default_factory=dict)


class ExtractionPayload(DynamicBaseModel):
    """Payload for data extraction steps."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    attribute: str | None = None
    script: str | None = Field(None, alias="expression")
    region: dict[str, int] | None = None  # {"x": 0, "y": 0, "w": 100, "h": 100}
    wait_for_selector: str | None = None
    timeout_ms: int = 5000

    # Loop detail collection
    data_capture: dict[str, str] = Field(default_factory=dict)


class BashPayload(DynamicBaseModel):
    """Payload for a bash step that runs a shell command."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    command: str
    key: str = "bash_output"
    timeout: int | float = Field(default=30, ge=1)
    continue_on_error: bool = False


# Unified Payload Type
MacroPayload = (
    NavigationPayload
    | InteractionPayload
    | ControlPayload
    | ExtractionPayload
    | BashPayload
    | dict[str, Any]
)


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
        steps = values.get('steps', []) if isinstance(values, dict) else getattr(values, 'steps', [])
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
                raise ValueError(f"Duplicate step number '{num}' found at path '{path}'")
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


class VerificationStatus(str, Enum):
    """验证状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_FAILED = "partial_failed"


class StepExecutionStatus(str, Enum):
    """单步执行状态"""

    PENDING = "pending"
    PASSED = "passed"  # 按原计划执行成功
    ADAPTED = "adapted"  # 经修正后执行成功
    FAILED = "failed"  # 执行失败
    SKIPPED = "skipped"  # 被跳过
    TIMEOUT = "timeout"  # 超时
    REDUNDANT = "redundant"  # 被识别为冗余


class RedundancyType(str, Enum):
    """冗余类型"""

    LOW_VALUE_ACTION = "low_value_action"  # 低价值动作（如 mouse_move）
    DUPLICATE_ACTION = "duplicate_action"  # 重复动作
    UNNECESSARY_WAIT = "unnecessary_wait"  # 不必要的等待
    ORPHAN_ACTION = "orphan_action"  # 孤立的无效动作
    NONE = "none"
    UNKNOWN = "unknown"


class AnomalyType(str, Enum):
    """异常类型"""

    COORDINATE_DRIFT = "coordinate_drift"  # 坐标漂移
    ELEMENT_NOT_FOUND = "element_not_found"  # 元素未找到
    ELEMENT_OBSCURED = "element_obscured"  # 元素被遮挡
    STATE_MISMATCH = "state_mismatch"  # 状态不匹配
    LOADING_TIMEOUT = "loading_timeout"  # 加载超时
    UNEXPECTED_FLOW = "unexpected_flow"  # 意外流程分支
    DATA_MISMATCH = "data_mismatch"  # 数据不匹配
    ENVIRONMENT_ERROR = "environment_error"  # 环境错误
    UNKNOWN = "unknown"  # 未知异常


class ExecutionMode(str, Enum):
    """执行模式"""

    DETERMINISTIC = "deterministic"  # 确定性执行
    HYBRID = "hybrid"  # 混合模式
    AGENTIC = "agentic"  # 完全 Agent 模式


class EnvironmentConfig(DynamicBaseModel):
    """验证环境配置"""

    platform: str = "mobile"  # web / android / desktop
    device_id: str | None = None
    browser_config: dict[str, Any] | None = None
    resolution: tuple | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)


class RoundConfig(DynamicBaseModel):
    """单轮验证配置"""

    round_name: str = "default"
    environment_overrides: dict[str, Any] = Field(default_factory=dict)
    inject_anomalies: list[str] = Field(default_factory=list)
    timeout_per_step: int = 30


class VerificationAgentConfig(DynamicBaseModel):
    """Agent 行为配置"""

    llm_model: str | None = None  # Must be provided explicitly
    max_retries_per_step: int = 3
    allow_strategy_adaptation: bool = True
    conservative_mode: bool = True  # Default to True to stop on failure
    enable_screenshot_analysis: bool = True


class EvolutionRule(DynamicBaseModel):
    """Rule for transforming a step based on anomaly type"""

    name: str
    anomaly_type: AnomalyType
    description: str
    priority: int = 0


class EvolutionContext(DynamicBaseModel):
    """Context for macro evolution"""

    original_macro: list[dict[str, Any]]
    step_results: list[StepResult]
    evolution_records: list[MacroEvolutionRecord]
    target_platform: str = "web"

    # Track which steps have been modified
    modified_steps: set[int] = Field(default_factory=set)

    # Track added steps (insertions)
    inserted_steps: dict[int, list[dict[str, Any]]] = Field(default_factory=dict)


class HealingDecision(DynamicBaseModel):
    """Result of a self-healing policy check."""

    allowed: bool
    reason: str
    # Source of the decision for debugging
    source: str  # "global" | "skill" | "execution" | "allowed"


class RedundancyCheckResult(DynamicBaseModel):
    """冗余检查结果"""

    is_redundant: bool = False
    redundancy_type: RedundancyType = RedundancyType.UNKNOWN
    reason: str = ""
    similar_to_step: int | None = None  # 如果是重复的，指向哪个步骤
    suggested_action: str = "keep"  # keep / skip / merge / remove


class AdaptationRecord(DynamicBaseModel):
    """修正记录

    支持步骤修改和额外步骤插入：
    - adapted_strategy: 修改后的主步骤
    - additional_steps: 额外添加的步骤（如前置等待、弹窗关闭等）
    """

    anomaly_type: AnomalyType = AnomalyType.UNKNOWN
    original_strategy: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    adapted_strategy: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    reasoning: str = ""
    success: bool = False
    attempt_number: int = 1

    # 额外步骤（在 adapted_strategy 之前执行）
    additional_steps: list[MacroStep] = Field(default_factory=list)


class ExecutionDetail(DynamicBaseModel):
    """执行详情"""

    pre_state: dict[str, Any] | None = None
    action_taken: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    post_state: dict[str, Any] | None = None
    screenshot_path: str | None = None
    ui_dump: dict[str, Any] | None = None


class StepResult(DynamicBaseModel):
    """单步执行结果"""

    step_number: int
    original_step: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    status: StepExecutionStatus = StepExecutionStatus.PENDING

    execution: ExecutionDetail | None = None
    adaptations: list[AdaptationRecord] = Field(default_factory=list)

    execution_time_ms: int = 0
    error_message: str | None = None

    # 修正后的实际执行参数（用于宏进化）
    effective_parameters: MacroStep | None = None

    # 冗余检查信息
    redundancy_check: RedundancyCheckResult | None = None


class MacroEvolutionRecord(DynamicBaseModel):
    """宏进化记录

    支持步骤修改和额外步骤插入：
    - evolved_step: 修改后的主步骤
    - additional_steps: 额外添加的步骤（如前置等待、弹窗关闭等）
    """

    original_step: MacroStep
    evolved_step: MacroStep
    evolution_reason: str
    confidence: float = 1.0

    # 额外步骤（在 evolved_step 之前执行）
    additional_steps: list[MacroStep] = Field(default_factory=list)


class RoundReport(DynamicBaseModel):
    """单轮验证报告"""

    round_number: int
    round_name: str
    status: VerificationStatus = VerificationStatus.PENDING

    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    adapted_steps: int = 0
    skipped_steps: int = 0

    step_results: list[StepResult] = Field(default_factory=list)
    environment_snapshot: dict[str, Any] | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None


class ReportSummary(DynamicBaseModel):
    """报告汇总"""

    overall_success_rate: float = 0.0
    adaptation_rate: float = 0.0
    max_round_variance: float = 0.0
    average_execution_time_ms: int = 0
    total_anomalies_detected: int = 0
    total_adaptations_applied: int = 0

    # 冗余检测统计
    total_steps_checked: int = 0
    redundant_steps_count: int = 0
    redundant_steps_by_type: dict[str, int] = Field(default_factory=dict)
    estimated_time_saved_ms: int = 0  # 跳过冗余步骤节省的时间


class VerificationIssue(DynamicBaseModel):
    """验证问题"""

    severity: str = "warning"  # critical / warning / info
    category: str = ""
    description: str = ""
    affected_steps: list[int | str] = Field(default_factory=list)
    suggestion: str | None = None


class VerificationReport(DynamicBaseModel):
    """详细验证报告"""

    summary: ReportSummary = Field(default_factory=ReportSummary)
    rounds: list[RoundReport] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    optimization_stats: dict[str, Any] | None = None  # MacroOptimizer 统计信息


class VerificationRequest(DynamicBaseModel):
    """验证请求"""

    macro_script: list[MacroStep]
    instructions: str | None = None
    session_id: str | None = None
    thread_id: str | None = None

    target_environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    max_rounds: int = 2
    round_configs: list[RoundConfig] = Field(default_factory=list)
    agent_config: VerificationAgentConfig | None = None

    output_mode: str = "evolved"  # evolved / report_only


class VerificationResponse(DynamicBaseModel):
    """验证响应"""

    success: bool = False
    status: VerificationStatus = VerificationStatus.PENDING

    evolved_macro: list[MacroStep] | None = None
    execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.0

    verification_report: VerificationReport = Field(default_factory=VerificationReport)
    evolution_records: list[MacroEvolutionRecord] = Field(default_factory=list)

    processing_time_seconds: float = 0.0
    rounds_completed: int = 0

    error_message: str | None = None


class AIAnalysisResult(DynamicBaseModel):
    """Result of agentic analysis of verification data"""

    issues: list[VerificationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    recommended_execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.5
    qualitative_assessment: str = ""


class OptimizationResult(DynamicBaseModel):
    original_steps: int
    optimized_steps: int
    removed_steps: int
    merged_steps: int
    time_saved_ms: int
    strategies_applied: list[str] = Field(default_factory=list)

    @property
    def reduction_ratio(self) -> float:
        if self.original_steps == 0:
            return 0.0
        return (self.original_steps - self.optimized_steps) / self.original_steps


class ActionDecision(DynamicBaseModel):
    """Decision made by the reasoning engine"""

    action: str  # 'execute', 'correct', 'skip', 'retry', 'abort'
    reasoning: str
    suggested_step: dict[str, Any] | None = None
    additional_steps: list[dict[str, Any]] = []
    confidence: float


class InterferenceConfig(DynamicBaseModel):
    """Configuration for interference injection"""

    enabled: bool = False
    type: str = "none"  # none, delay, chaos, network_degradation
    intensity: float = 0.3  # 0.0 - 1.0
    targets: list[str] = Field(default_factory=list)  # step types to target
    custom_params: dict[str, Any] = Field(default_factory=dict)


class RoundContext(DynamicBaseModel):
    """Context passed between rounds"""

    round_number: int
    previous_reports: list[RoundReport]
    shared_state: dict[str, Any] = Field(default_factory=dict)
    accumulated_anomalies: list[dict[str, Any]] = Field(default_factory=list)


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


class MacroVerificationResult(DynamicBaseModel):
    """Lightweight dry-run verification result for a macro script."""

    status: str
    success: bool
    missing_keys: list[str] = []
    extracted_count: int = 0
    error: str | None = None


class VerificationSummary(DynamicBaseModel):
    success_rate: float
    adaptation_rate: float
    anomalies_detected: int
    adaptations_applied: int


class ModeRecommendation(DynamicBaseModel):
    can_execute: bool
    recommended_mode: str
    reason: str
    confidence: float


class MacroEvolutionResult(DynamicBaseModel):
    success: bool
    original_macro: list[dict[str, Any]] | MacroScript | str
    evolved_macro: list[dict[str, Any]] | None = None
    execution_mode: str | None = None
    confidence: float | None = None
    improvements: list[str] = Field(default_factory=list)
    report: VerificationReport | None = None
    error: str | None = None
