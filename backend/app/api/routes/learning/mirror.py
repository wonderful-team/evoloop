"""Mirror sub-router — device mirroring, event capture, extract points."""

import json
import logging
import subprocess
import time
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select

from app.api.deps import CurrentUserOptional, require_benefit
from app.core.environment.controllers.mirror_session import mirror_manager
from app.core.learning.schemas import (
    AndroidExtractPointRequest,
    AndroidExtractPointResponse,
    DeviceResolutionResponse,
    DomEventsRequest,
    GlobalEventsRequest,
    MirrorDevicesResponse,
    MirrorPersistResponse,
    MirrorRecordingResponse,
    MirrorSessionResponse,
    PersistMirrorEventsRequest,
    StartMirrorRecordingRequest,
    StartMirrorRequest,
    StopMirrorRequest,
    StopMirrorResponse,
    UploadScreenshotResponse,
)
from app.infrastructure.database import session_scope
from app.infrastructure.drivers.adb import adb_driver
from app.models import TraceEvent

from ._shared import _active_sessions

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_trace_event(
    *,
    member_id: int,
    session_id: str,
    thread_id: str | None,
    step_number: int,
    node_name: str,
    action_type: str,
    timestamp: int,
    event_type: str,
    source: str,
    app_name: str | None,
    payload: dict,
    state_context: dict,
    target_selector: str | None = None,
    target_text: str | None = None,
    mouse_x: float | None = None,
    mouse_y: float | None = None,
    window_title: str | None = None,
    action_payload: dict | None = None,
) -> TraceEvent:
    """Single construction site for recorder TraceEvent rows.

    All four recorder endpoints persist the same shape; only the payload
    contents and context tag differ. ``action_payload`` defaults to the
    event payload itself.
    """
    return TraceEvent(
        member_id=member_id,
        session_id=session_id,
        recording_session_id=session_id,
        thread_id=thread_id,
        step_number=step_number,
        node_name=node_name,
        action_type=action_type,
        timestamp=timestamp,
        event_type=event_type,
        target_selector=target_selector,
        target_text=target_text,
        payload=payload,
        mouse_x=mouse_x,
        mouse_y=mouse_y,
        source=source,
        app_name=app_name,
        window_title=window_title,
        state_snapshot=state_context,
        action_payload=json.dumps(action_payload if action_payload is not None else payload),
        # Recorder endpoints persist USER-recorded events — human by definition.
        is_human_action=True,
    )


@router.get("/mirror/devices", response_model=MirrorDevicesResponse)
async def list_mirror_devices(current_user: CurrentUserOptional = None):
    """List connected Android devices for mirroring."""
    devices = adb_driver.list_devices()
    scrcpy_available = False
    try:
        subprocess.run(["scrcpy", "--version"], capture_output=True, text=True)
        scrcpy_available = True
    except FileNotFoundError:
        pass

    return MirrorDevicesResponse(devices=devices, scrcpy_available=scrcpy_available)


@router.post("/mirror/start", response_model=MirrorSessionResponse, dependencies=[Depends(require_benefit("desktop_control"))])
async def start_mirror_session(body: StartMirrorRequest):
    """Start a scrcpy mirroring session."""
    session = await mirror_manager.create_session(body.device_id, record_video=body.record_video)
    if not session.is_active:
        raise HTTPException(status_code=500, detail=session.error or "Failed to start mirroring session")

    _active_sessions[session.session_id] = {
        "thread_id": "global",
        "task_name": f"Android Mirror ({body.device_id})",
        "started_at": datetime.utcnow(),
    }

    return MirrorSessionResponse(success=True, session_id=session.session_id, device_id=session.device_id)


@router.post("/mirror/start-recording", response_model=MirrorRecordingResponse, dependencies=[Depends(require_benefit("skill_learning"))])
async def start_mirror_recording(body: StartMirrorRecordingRequest):
    """Start event recording for an active mirror session."""
    success = mirror_manager.start_recording(body.session_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to start recording. Session may not be active or recording already started.")
    return MirrorRecordingResponse(success=True, message="Recording started", session_id=body.session_id)


@router.post("/mirror/stop", response_model=StopMirrorResponse)
async def stop_mirror_session(body: StopMirrorRequest, current_user: CurrentUserOptional = None):
    """Stop an active mirroring session."""
    result = mirror_manager.stop_session(body.session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")

    _active_sessions.pop(body.session_id, None)

    async with session_scope() as db:
        stmt = select(func.count(TraceEvent.id)).where(TraceEvent.recording_session_id == body.session_id)
        total_count_result = await db.execute(stmt)
        total_count = total_count_result.scalar() or 0

    return StopMirrorResponse(
        success=True,
        message="Mirroring session stopped",
        video_path=result.get("video_path"),
        session_id=result.get("session_id"),
        event_count=total_count,
    )


@router.get("/mirror/device/{device_id}/resolution", response_model=DeviceResolutionResponse)
async def get_device_resolution(device_id: str, current_user: CurrentUserOptional = None):
    """Get Android device screen resolution via ADB."""
    try:
        size = adb_driver.get_screen_size(device_id)
        if not size:
            return DeviceResolutionResponse(width=1080, height=1920)
        return DeviceResolutionResponse(width=size[0], height=size[1])
    except Exception as e:
        logger.error(f"Failed to get device resolution: {e}")
        return DeviceResolutionResponse(width=1080, height=1920)


@router.post("/mirror/events", response_model=MirrorPersistResponse)
async def persist_mirror_events(body: PersistMirrorEventsRequest, current_user: CurrentUserOptional = None):
    """Persist Android mirror events (final flush / retry for real-time events)."""
    events = mirror_manager.get_session_events(body.session_id)
    if not events:
        return MirrorPersistResponse(
            success=True,
            message="No events to persist (already persisted in real-time)",
            count=0,
        )

    async with session_scope() as db:
        stmt = (
            select(TraceEvent)
            .where(TraceEvent.member_id == (current_user.id if current_user else 0))
            .where(TraceEvent.recording_session_id == body.session_id)
        )
        result = await db.execute(stmt)
        existing_count = len(result.scalars().all())

        if existing_count >= len(events):
            return MirrorPersistResponse(
                success=True,
                message="Events already persisted in real-time",
                count=existing_count,
            )

    try:
        async with session_scope() as db:
            for i, event_data in enumerate(events):
                payload_data = event_data.get("payload", {})
                relative_ms = event_data.get("timestamp", 0)
                node_name = event_data.get("node_name") or payload_data.get("device_id") or "android_mirror"
                source = event_data.get("source") or "mobile"
                thread_id = body.thread_id or "global"

                trace_event = _build_trace_event(
                    member_id=current_user.id if current_user else 0,
                    session_id=body.session_id,
                    thread_id=thread_id,
                    step_number=i,
                    node_name=node_name,
                    action_type="user_interaction",
                    timestamp=relative_ms,
                    event_type=event_data["event_type"],
                    target_selector=event_data.get("target_selector"),
                    target_text=event_data.get("target_text"),
                    payload=payload_data,
                    mouse_x=payload_data.get("x"),
                    mouse_y=payload_data.get("y"),
                    source=source,
                    app_name=payload_data.get("package_name"),
                    state_context={"context": "android_mirror"},
                )
                db.add(trace_event)

                if i < 5:
                    logger.info(f"[persist_mirror_events] Event {i}: {event_data['event_type']} at {relative_ms}ms")

        return MirrorPersistResponse(success=True, message="Events persisted", count=len(events))
    except Exception as e:
        logger.exception(f"Failed to persist mirror events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist events: {str(e)}")


@router.post("/global/events", response_model=MirrorPersistResponse)
async def persist_global_events(body: GlobalEventsRequest, current_user: CurrentUserOptional = None):
    """Persist global desktop events to backend."""
    if not body.events:
        return MirrorPersistResponse(success=True, message="No events to persist", count=0)

    try:
        async with session_scope() as db:
            for i, event in enumerate(body.events):
                payload = {
                    "key": event.key,
                    "mouse_button": event.mouse_button,
                    "position": event.position,
                    "process_id": event.process_id,
                    "platform": "macos",
                    "relative_timestamp_ms": int(event.timestamp),
                }
                payload = {k: v for k, v in payload.items() if v is not None}

                source = event.source or "global"
                app_name = event.app_name

                if source == "mobile":
                    session = mirror_manager.get_session(body.session_id)
                    if session:
                        resolved_pkg = session.get_current_package()
                        if resolved_pkg:
                            app_name = resolved_pkg

                if app_name:
                    payload["package_name"] = app_name

                trace_event = _build_trace_event(
                    member_id=current_user.id if current_user else 0,
                    session_id=body.session_id,
                    thread_id=body.thread_id,
                    step_number=i,
                    node_name=app_name or "global_recorder",
                    action_type="user_interaction",
                    timestamp=int(event.timestamp),
                    event_type=event.event_type,
                    target_selector=f"global://screen/{event.position[0]}/{event.position[1]}" if event.position else None,
                    target_text=event.window_title,
                    payload=payload,
                    mouse_x=event.position[0] if event.position else None,
                    mouse_y=event.position[1] if event.position else None,
                    source=source,
                    app_name=app_name,
                    window_title=event.window_title,
                    state_context={"context": "global_recorder"},
                )
                db.add(trace_event)

                if i < 5:
                    logger.info(f"[persist_global_events] Event {i}: {event.event_type} at {int(event.timestamp)}ms, app={event.app_name}")

        return MirrorPersistResponse(success=True, message="Global events persisted", count=len(body.events))
    except Exception as e:
        logger.exception(f"Failed to persist global events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist events: {str(e)}")


@router.post("/dom/events", response_model=MirrorPersistResponse)
async def persist_dom_events(body: DomEventsRequest, current_user: CurrentUserOptional = None):
    """Persist DOM events to backend."""
    if not body.events:
        return MirrorPersistResponse(success=True, message="No events to persist", count=0)

    try:
        async with session_scope() as db:
            for i, event in enumerate(body.events):
                payload = {
                    "value": event.value,
                    "url": event.url,
                    "xpath": event.xpath,
                    "coordinates": event.coordinates,
                    "platform": "web",
                    "relative_timestamp_ms": int(event.timestamp),
                }
                payload = {k: v for k, v in payload.items() if v is not None}

                is_region_extract = event.event_type == "region_extract"
                action_type = "region_extract" if is_region_extract else "user_interaction"
                node_name = "region_marker" if is_region_extract else "dom_recorder"

                trace_event = _build_trace_event(
                    member_id=current_user.id if current_user else 0,
                    session_id=body.session_id,
                    thread_id=body.thread_id,
                    step_number=i,
                    node_name=node_name,
                    action_type=action_type,
                    timestamp=int(event.timestamp),
                    event_type=event.event_type,
                    target_selector=event.selector,
                    target_text=event.target_text,
                    payload=payload,
                    source="dom",
                    app_name=event.url if not is_region_extract else "screen_region",
                    state_context={"context": node_name, "url": event.url},
                )
                db.add(trace_event)

                if i < 5:
                    logger.info(f"[persist_dom_events] Event {i}: {event.event_type} at {int(event.timestamp)}ms, selector={event.selector}")

        return MirrorPersistResponse(success=True, message="DOM events persisted", count=len(body.events))
    except Exception as e:
        logger.exception(f"Failed to persist DOM events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to persist events: {str(e)}")


@router.post("/assets/upload-screenshot", response_model=UploadScreenshotResponse)
async def upload_screenshot(file: UploadFile = File(...), current_user: CurrentUserOptional = None):
    """Upload a screenshot for a skill step."""
    try:
        from app.infrastructure.vision.storage import screenshot_storage

        content = await file.read()
        file_path = screenshot_storage.save_screenshot(
            image_data=content,
            purpose="dataset",
            platform="macos",
            suffix=f"upload_{file.filename}",
        )
        return UploadScreenshotResponse(success=True, path=file_path, message="Screenshot uploaded successfully")
    except Exception as e:
        logger.error(f"Failed to upload screenshot: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload screenshot: {str(e)}")


@router.post("/mirror/extract-point", response_model=AndroidExtractPointResponse)
async def create_android_extract_point(body: AndroidExtractPointRequest, current_user: CurrentUserOptional = None):
    """Mark a data extraction point during Android mirror recording."""
    timestamp_ms = body.timestamp_ms or int(time.time() * 1000)

    async with session_scope() as db:
        region_width = body.width if body.width is not None else 0.02
        region_height = body.height if body.height is not None else 0.02

        trace_event = _build_trace_event(
            member_id=current_user.id if current_user else 0,
            session_id=body.session_id,
            thread_id=body.thread_id or "global",
            step_number=0,
            node_name="android_region_marker",
            action_type="region_extract",
            timestamp=timestamp_ms,
            event_type="region_extract",
            target_selector=f"android://screen/{body.x:.4f}/{body.y:.4f}",
            target_text=body.note or "Android mirror extract point",
            payload={
                "coordinates": {
                    "x": body.x,
                    "y": body.y,
                    "width": region_width,
                    "height": region_height,
                },
                "platform": "android",
                "relative_timestamp_ms": timestamp_ms,
            },
            source="android",
            app_name="android_mirror",
            state_context={"context": "android_region_marker"},
            action_payload={
                "x": body.x,
                "y": body.y,
                "width": region_width,
                "height": region_height,
            },
        )
        db.add(trace_event)
        await db.flush()
        await db.refresh(trace_event)

        region_type = "area" if body.width and body.height else "point"
        logger.info(f"[AndroidMirror] Extract point: id={trace_event.id}, session={body.session_id}, pos=({body.x:.3f}, {body.y:.3f}), type={region_type}")

        return AndroidExtractPointResponse(
            id=trace_event.id,
            session_id=body.session_id,
            x=body.x,
            y=body.y,
            width=region_width,
            height=region_height,
            timestamp_ms=timestamp_ms,
            note=body.note or "Android mirror extract point",
            created_at=trace_event.created_at,
        )


@router.get("/mirror/{session_id}/extract-points", response_model=list[AndroidExtractPointResponse])
async def list_android_extract_points(session_id: str, current_user: CurrentUserOptional = None):
    """Get all extract points for a session."""
    async with session_scope() as db:
        stmt = select(TraceEvent).where(TraceEvent.member_id == (current_user.id if current_user else 0)).where(
            TraceEvent.recording_session_id == session_id,
            TraceEvent.action_type == "region_extract"
        ).order_by(TraceEvent.timestamp)

        result = await db.execute(stmt)
        events = result.scalars().all()

        extract_points = []
        for e in events:
            coords = e.payload.get("coordinates") if e.payload else {}
            extract_points.append(
                AndroidExtractPointResponse(
                    id=e.id,
                    session_id=e.recording_session_id or session_id,
                    x=coords.get("x", 0) if coords else 0,
                    y=coords.get("y", 0) if coords else 0,
                    width=coords.get("width") if coords else None,
                    height=coords.get("height") if coords else None,
                    timestamp_ms=int(e.timestamp) if e.timestamp else 0,
                    note=e.target_text or "Android mirror extract point",
                    created_at=e.created_at,
                )
            )

        return extract_points
