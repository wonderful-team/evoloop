"""Learning schemas."""

from typing import Any

from pydantic import BaseModel


class GlobalEventData(BaseModel):
    """全局桌面事件数据"""

    timestamp: float
    event_type: str  # "mouse_click", "key_press"
    key: str | None = None
    mouse_button: str | None = None
    position: tuple[float, float] | None = None
    window_title: str | None = None
    app_name: str | None = None
    process_id: int | None = None
    source: str | None = (
        None  # [NEW] Optional source override (e.g. "mobile" for mirror clicks)
    )


class DomEventData(BaseModel):
    """DOM 事件数据"""

    timestamp: float
    event_type: str  # "click", "input", "scroll", etc.
    selector: str | None = None
    target_text: str | None = None
    value: str | None = None
    url: str | None = None
    xpath: str | None = None
    coordinates: dict | None = None  # {x, y, width, height}


class RecordingSessionItem(BaseModel):
    session_id: str
    thread_id: str
    task_name: str | None = None
    started_at: str
    event_count: int


class PreviewVideoInfo(BaseModel):
    path: str
    duration: float
    resolution: str
    fps: float


class PreviewEventsSummary(BaseModel):
    total: int
    types: list[str]


class PreviewKeyframeSummary(BaseModel):
    planned: int
    est_frames: int
    est_tokens: str
    details: list[dict[str, Any]]
