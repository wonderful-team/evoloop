"""Learning schemas."""

from datetime import datetime
from typing import Any

from app.core.learning.schemas.events import (
    PreviewEventsSummary,
    PreviewKeyframeSummary,
    PreviewVideoInfo,
    RecordingSessionItem,
)
from app.core.learning.schemas.skills import SkillDetailResponse, SkillDTO
from app.core.schemas import BaseAPIResponse, ListResponse


class PaginatedSkillsResponse(ListResponse[SkillDTO]):
    pass


class RecordingSessionsResponse(BaseAPIResponse):
    sessions: list[RecordingSessionItem]


class SynthesizeSkillResponse(BaseAPIResponse):
    skill_id: int
    skill_name: str
    skill_yaml: str


class ImportSkillsResponse(BaseAPIResponse):
    results: dict[str, Any]


class UpdateSkillResponse(BaseAPIResponse):
    skill: SkillDetailResponse


class UpdateSkillFromYamlResponse(BaseAPIResponse):
    step_count: int


class ExecuteSkillResponse(BaseAPIResponse):
    execution_mode: str


class MirrorDevicesResponse(BaseAPIResponse):
    devices: list[dict[str, Any]]
    scrcpy_available: bool


class MirrorSessionResponse(BaseAPIResponse):
    session_id: str
    device_id: str


class MirrorRecordingResponse(BaseAPIResponse):
    session_id: str


class MirrorPersistResponse(BaseAPIResponse):
    count: int


class StopMirrorResponse(BaseAPIResponse):
    video_path: str | None = None
    session_id: str
    event_count: int


class DeviceResolutionResponse(BaseAPIResponse):
    width: int
    height: int


class ValidateSkillResponse(BaseAPIResponse):
    validation: dict[str, Any] | None = None
    error: str | None = None


class PreviewRecordingDataResponse(BaseAPIResponse):
    video_info: PreviewVideoInfo
    events: PreviewEventsSummary
    keyframes: PreviewKeyframeSummary


class CleanupRecordingResponse(BaseAPIResponse):
    deleted: dict[str, Any]


class CreateSkillFromYamlResponse(BaseAPIResponse):
    skill_id: int
    skill_name: str
    step_count: int


# ============ Endpoints ============


class StartRecordingResponse(BaseAPIResponse):
    session_id: str


class StopRecordingResponse(BaseAPIResponse):
    session_id: str
    event_count: int


# In-memory session tracking

class UploadScreenshotResponse(BaseAPIResponse):
    path: str


class SynthesizeFromRecordingResponse(BaseAPIResponse):
    """从录制合成 Skill 的响应"""
    skill_id: int | None
    skill_name: str | None
    skill_yaml: str | None
    macro_script: str | None = None  # YAML format
    verification: dict | None = None
    error: str | None
    processing_time_seconds: float
    frames_analyzed: int
    events_processed: int


class AnnotationResponse(BaseAPIResponse):
    """标注响应"""
    id: int
    session_id: str
    annotation_type: str
    video_timestamp_ms: int
    region: dict | None
    user_note: str | None
    created_at: datetime


class AndroidExtractPointResponse(BaseAPIResponse):
    """Android镜像提取点标记响应"""
    id: int
    session_id: str
    x: float
    y: float
    width: float | None  # 区域宽度（相对坐标 0-1）
    height: float | None  # 区域高度（相对坐标 0-1）
    timestamp_ms: int | None
    note: str | None
    created_at: datetime


class ValidateYamlResponse(BaseAPIResponse):
    """Response from YAML validation."""
    valid: bool
    errors: list[str]
    step_count: int = 0
