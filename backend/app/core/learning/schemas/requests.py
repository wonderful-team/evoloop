"""Learning schemas."""

from datetime import datetime
from typing import Any, cast

from pydantic import BaseModel, Field
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.responses import BaseAPIResponse, ListResponse
from app.models.schemas.base import ScopedRequest


class HumanInputRequestOut(BaseModel):
    id: str
    thread_id: str
    request_type: str
    prompt: str
    options: list[str] | None = None
    context: str | None = None
    default_value: str | None = None
    created_at: str
    status: str


class ExecuteSkillRequest(ScopedRequest):
    thread_id: str
    params: SkillExecutionParams
    project_id: int | None = 1
    execution_mode: str | None = None  # Optional: override skill's execution mode


class RespondRequest(BaseModel):
    response: Any


class StartMirrorRequest(BaseModel):
    device_id: str
    record_video: bool = True


class StopMirrorRequest(BaseModel):
    session_id: str


class StartMirrorRecordingRequest(BaseModel):
    """[NEW] Request to start event recording for an active mirror session."""
    session_id: str


class PersistMirrorEventsRequest(ScopedRequest):
    """请求模型：持久化存储镜像事件"""
    session_id: str
    thread_id: str | None = None  # [NEW] Optional thread binding


class GlobalEventsRequest(ScopedRequest):
    """请求模型：接收全局桌面事件"""
    session_id: str
    thread_id: str
    events: list[GlobalEventData]


class DomEventsRequest(ScopedRequest):
    """请求模型：接收 DOM 事件"""
    session_id: str
    thread_id: str
    events: list[DomEventData]


class ImportSkillsRequest(BaseModel):
    directory: str


class StartRecordingRequest(ScopedRequest):
    thread_id: str
    task_name: str | None = None


class SynthesizeRequest(ScopedRequest):
    thread_id: str
    session_id: str | None = None
    auto_optimize: bool = True


class UpdateSkillRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    namespace: str | None = None
    trigger_patterns: list[str] | None = None
    parameters: list[dict[str, Any]] | None = None
    instructions: str | None = None
    preconditions: list[dict[str, Any]] | None = None
    execution_mode: str | None = None
    macro_script: str | None = None  # YAML format


class SynthesizeFromRecordingRequest(ScopedRequest):
    """从录制合成 Skill 的请求（v3 统一版）

    [v3 统一架构] 所有录制类型（Desktop/Global/Android）的事件都已通过
    实时 API（/global/events, /dom/events, /mirror/events）持久化到数据库，
    合成时统一从数据库读取，不再支持通过请求体传入事件。
    """
    video_path: str  # Tauri 返回的视频文件路径
    session_id: str  # 关联事件的 session_id（用于从数据库查询事件）
    task_description: str  # 用户描述的任务
    thread_id: str | None = None


class AndroidExtractPointRequest(ScopedRequest):
    """Android镜像实时提取点标记请求 - 支持区域标记"""
    session_id: str
    thread_id: str | None = None
    x: float  # 区域左上角 X 坐标（相对坐标 0-1）
    y: float  # 区域左上角 Y 坐标（相对坐标 0-1）
    width: float | None = None  # 区域宽度（相对坐标 0-1），null 表示单点标记
    height: float | None = None  # 区域高度（相对坐标 0-1），null 表示单点标记
    timestamp_ms: int | None = None  # 可选：录制时间戳
    note: str | None = None  # 可选：用户备注


class SmartSynthesisRequest(ScopedRequest):
    """智能合成请求"""
    session_id: str
    thread_id: str | None = None
    task_goal: str
    annotation_ids: list[int] | None = None  # 指定使用哪些标注，null表示使用全部


class CreateSkillFromYamlRequest(BaseModel):
    """Request to create a skill from YAML macro definition."""
    name: str
    description: str | None = None
    namespace: str | None = None
    yaml_content: str


class ValidateYamlRequest(BaseModel):
    """Request to validate YAML macro format."""
    yaml_content: str
