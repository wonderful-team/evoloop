"""Synthesis sub-router — multimodal skill synthesis from recordings."""

import json
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUserOptional
from app.core.events.publishers import publish_macro_mutated, publish_skill_mutated
from app.core.learning.macro.service import MacroService
from app.core.learning.multimodal_synthesizer import (
    MultimodalSkillSynthesizer,
    RecordingSession,
)
from app.core.learning.schemas import (
    AnnotationResponse,
    CleanupRecordingResponse,
    PreviewEventsSummary,
    PreviewKeyframeSummary,
    PreviewRecordingDataResponse,
    PreviewVideoInfo,
    SynthesizeFromRecordingRequest,
    SynthesizeFromRecordingResponse,
)
from app.core.learning.skills.lifecycle import create_from_synthesis
from app.infrastructure.database import session_scope
from app.utils.parameters import normalize_parameters

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/skills/synthesize-from-recording", response_model=SynthesizeFromRecordingResponse
)
async def synthesize_from_recording(
    request: SynthesizeFromRecordingRequest, current_user: CurrentUserOptional = None
):
    """Synthesize a skill from a video recording (multimodal v3)."""
    start_time = time.time()
    logger.info(
        f"[v3] Received synthesis request: session={request.session_id}, video={request.video_path}"
    )

    try:
        if not os.path.exists(request.video_path):
            raise HTTPException(
                status_code=400, detail=f"Video file not found: {request.video_path}"
            )

        synthesizer = MultimodalSkillSynthesizer()
        recording = RecordingSession(
            video_path=request.video_path,
            session_id=request.session_id,
            task_description=request.task_description,
            thread_id=request.thread_id,
        )

        # SKILL.md export is handled by the SKILL_CREATED subscriber AFTER the
        # row commits below; a file-watcher re-import of that export finds the
        # pending_review row and skips it (see SkillImporter).
        result = await synthesizer.synthesize(recording)
        skill_data = result["skill"]
        macro_script = result.get("macro_script")
        metadata = result["metadata"]

        async with session_scope() as db:
            db_skill = await create_from_synthesis(
                db,
                member_id=current_user.id if current_user else 0,
                name=skill_data["name"],
                description=skill_data["description"],
                namespace=skill_data.get("namespace", "misc"),
                trigger_patterns=skill_data.get("trigger_patterns", []),
                parameters=skill_data.get("parameters", []),
                instructions=skill_data["instructions"],
                source_session_id=skill_data.get("source_session_id"),
                source_thread_id=skill_data.get("source_thread_id"),
                skill_source="multimodal_record",
                validation_report={"status": "pending_verification"},
            )
            skill_data["name"] = db_skill.name

            verification = {"status": "skipped"}
            if macro_script:
                macro = await MacroService.create_for_skill(
                    db,
                    db_skill,
                    macro_script,
                    project_id=request.project_id,
                    member_id=current_user.id if current_user else 0,
                    source_thread_id=skill_data.get("source_thread_id"),
                )

                # Structural validation only — never execute the macro here
                from app.core.learning.macro.authoring import validate_macro_structure

                ok, error, step_count = validate_macro_structure(macro_script)
                verification = (
                    {
                        "status": "structure_valid",
                        "step_count": step_count,
                    }
                    if ok
                    else {
                        "status": "structure_invalid",
                        "error_message": error,
                    }
                )
                from app.core.learning.skills.lifecycle import patch_skill

                await patch_skill(db_skill, validation_report=verification)
                await db.flush()

        await publish_skill_mutated(skill_id=db_skill.id, action="create")
        if macro_script:
            await publish_macro_mutated(macro.id, action="create")

        skill_yaml = f"""---
name: {skill_data["name"]}
namespace: {skill_data.get("namespace", "misc")}
description: {skill_data["description"]}
trigger_patterns: {json.dumps(skill_data.get("trigger_patterns", []))}
parameters: {json.dumps(normalize_parameters(skill_data.get("parameters", [])))}
---

{skill_data["instructions"]}
"""

        processing_time = time.time() - start_time

        return SynthesizeFromRecordingResponse(
            success=True,
            skill_id=db_skill.id,
            skill_name=skill_data["name"],
            skill_yaml=skill_yaml,
            macro_script=macro_script,
            verification=verification,
            error=None,
            processing_time_seconds=round(processing_time, 2),
            frames_analyzed=metadata["frames_analyzed"],
            events_processed=metadata["events_processed"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Multimodal synthesis failed: {e}")
        processing_time = time.time() - start_time
        return SynthesizeFromRecordingResponse(
            success=False,
            skill_id=None,
            skill_name=None,
            skill_yaml=None,
            error=str(e),
            processing_time_seconds=round(processing_time, 2),
            frames_analyzed=0,
            events_processed=0,
        )


@router.get(
    "/skills/synthesize-from-recording/preview",
    response_model=PreviewRecordingDataResponse,
)
async def preview_recording_data(
    session_id: str, video_path: str, current_user: CurrentUserOptional = None
):
    """Preview recording data (debug) — returns keyframe plan without calling LLM."""
    from app.infrastructure.vision.video.compressor import KeyframeSelector

    try:
        synthesizer = MultimodalSkillSynthesizer()
        video_info = await synthesizer._get_video_info(video_path)
        events = await synthesizer._fetch_events(session_id)

        selector = KeyframeSelector()
        keyframes = selector.select_keyframes(
            events=events, video_duration=video_info.duration
        )

        return PreviewRecordingDataResponse(
            video_info=PreviewVideoInfo(
                path=video_path,
                duration=video_info.duration,
                resolution=f"{video_info.width}x{video_info.height}",
                fps=video_info.fps,
            ),
            events=PreviewEventsSummary(
                total=len(events),
                types=list({e.action_type for e in events}),
            ),
            keyframes=PreviewKeyframeSummary(
                planned=len(keyframes),
                est_frames=min(len(keyframes), 15),
                est_tokens=f"~{len(keyframes) * 1000}-{len(keyframes) * 1500}",
                details=[
                    {
                        "timestamp": k.timestamp,
                        "context": k.context,
                        "description": k.description,
                        "priority": k.priority,
                    }
                    for k in keyframes[:5]
                ],
            ),
        )
    except Exception as e:
        logger.exception(f"Preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/recordings/{session_id}/annotations", response_model=list[AnnotationResponse]
)
async def list_annotations(session_id: str, current_user: CurrentUserOptional = None):
    """Get all annotations (region_extract events from TraceEvent)."""
    from app.core.learning.trace.repository import trace_repository

    async with session_scope() as db:
        events = await trace_repository.get_by_session(
            session_id,
            member_id=current_user.id if current_user else 0,
            action_type="region_extract",
            db=db,
        )

        annotations = []
        for e in events:
            coords = e.payload.get("coordinates") if e.payload else None
            annotations.append(
                AnnotationResponse(
                    id=e.id,
                    session_id=e.recording_session_id or session_id,
                    annotation_type="extract",
                    video_timestamp_ms=int(e.timestamp) if e.timestamp else 0,
                    region={
                        "x": coords.get("x") if coords else None,
                        "y": coords.get("y") if coords else None,
                        "width": coords.get("width") if coords else None,
                        "height": coords.get("height") if coords else None,
                    }
                    if coords
                    else None,
                    user_note=e.target_text or "Screen region extraction",
                    created_at=e.created_at if e.created_at else datetime.now(),
                )
            )

        return annotations


@router.delete("/recordings/{session_id}", response_model=CleanupRecordingResponse)
async def cleanup_recording_session(
    session_id: str,
    video_path: str | None = None,
    current_user: CurrentUserOptional = None,
):
    """Clean up all data associated with a recording session."""
    deleted_counts = {"events": 0, "video_file": False}

    try:
        from app.core.learning.trace.repository import trace_repository

        async with session_scope() as db:
            deleted_counts["events"] = await trace_repository.delete_by_session(
                session_id,
                member_id=current_user.id if current_user else 0,
                db=db,
            )

        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                deleted_counts["video_file"] = True
                logger.info(f"[Cleanup] Deleted video file: {video_path}")
            except Exception as e:
                logger.exception(f"[Cleanup] Failed to delete video file {video_path}: {e}")

        logger.info(f"[Cleanup] Session {session_id} cleaned up: {deleted_counts}")

        return CleanupRecordingResponse(
            success=True,
            message=f"Recording session {session_id} cleaned up",
            deleted=deleted_counts,
        )
    except Exception as e:
        logger.exception(f"[Cleanup] Failed to cleanup session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
