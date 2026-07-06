"""Synthesis sub-router — multimodal and smart skill synthesis from recordings."""
import json
import logging
import os
import time
import traceback
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import delete, or_, select

from app.api.deps import CurrentUserOptional
from app.core.events.publishers import publish_skill_mutated
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
    SmartSynthesisRequest,
    SmartSynthesisResponse,
    SynthesisJobResponse,
    SynthesizeFromRecordingRequest,
    SynthesizeFromRecordingResponse,
)
from app.infrastructure.database import session_scope
from app.models import LearnedSkill, SynthesisJob, TraceEvent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/skills/synthesize-from-recording", response_model=SynthesizeFromRecordingResponse)
async def synthesize_from_recording(request: SynthesizeFromRecordingRequest, current_user: CurrentUserOptional = None):
    """Synthesize a skill from a video recording (multimodal v3)."""
    start_time = time.time()
    logger.info(f"[v3] Received synthesis request: session={request.session_id}, video={request.video_path}")

    try:
        if not os.path.exists(request.video_path):
            raise HTTPException(status_code=400, detail=f"Video file not found: {request.video_path}")

        synthesizer = MultimodalSkillSynthesizer()
        recording = RecordingSession(
            video_path=request.video_path,
            session_id=request.session_id,
            task_description=request.task_description,
            thread_id=request.thread_id
        )

        result = await synthesizer.synthesize(recording)
        skill_data = result["skill"]
        metadata = result["metadata"]

        async with session_scope() as db:
            base_name = skill_data["name"]
            unique_name = base_name
            counter = 1

            while True:
                stmt = select(LearnedSkill).where(or_(LearnedSkill.member_id == 0, LearnedSkill.member_id == (current_user.id if current_user else 0))).where(LearnedSkill.name == unique_name)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if not existing:
                    break
                unique_name = f"{base_name}_{counter}"
                counter += 1

            if unique_name != base_name:
                logger.info(f"Skill name collision resolved: {base_name} -> {unique_name}")
                skill_data["name"] = unique_name

            db_skill = LearnedSkill(member_id=current_user.id if current_user else 0,
                name=skill_data["name"],
                description=skill_data["description"],
                namespace=skill_data.get("namespace", "misc"),
                trigger_patterns=json.dumps(skill_data.get("trigger_patterns", [])),
                parameters=json.dumps(skill_data.get("parameters", [])),
                instructions=skill_data["instructions"],
                source_session_id=skill_data.get("source_session_id"),
                source_thread_id=skill_data.get("source_thread_id"),
                skill_source="multimodal_record",
                status="pending_review",
                is_active=True,
                execution_mode=skill_data.get("execution_mode", "agentic"),
                macro_script=skill_data.get("macro_script"),
                validation_report={"status": "pending_verification"},
            )
            db.add(db_skill)
            await db.flush()

            verification = {"status": "skipped"}
            if db_skill.macro_script:
                try:
                    verification = await synthesizer.verify_macro(db_skill.macro_script)
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Verification failed after saving DB: {e}")
                    verification = {"status": "failed", "error_message": str(e)}

                db_skill.validation_report = verification
                await db.flush()

        await publish_skill_mutated(skill_id=db_skill.id, action="create")

        skill_yaml = f"""---
name: {skill_data['name']}
namespace: {skill_data.get('namespace', 'misc')}
description: {skill_data['description']}
trigger_patterns: {json.dumps(skill_data.get('trigger_patterns', []))}
parameters: {json.dumps(skill_data.get('parameters', []))}
---

{skill_data['instructions']}
"""

        processing_time = time.time() - start_time

        return SynthesizeFromRecordingResponse(
            success=True,
            skill_id=db_skill.id,
            skill_name=skill_data["name"],
            skill_yaml=skill_yaml,
            macro_script=skill_data.get("macro_script"),
            verification=verification,
            error=None,
            processing_time_seconds=round(processing_time, 2),
            frames_analyzed=metadata["frames_analyzed"],
            events_processed=metadata["events_processed"]
        )

    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
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
            events_processed=0
        )


@router.get("/skills/synthesize-from-recording/preview", response_model=PreviewRecordingDataResponse)
async def preview_recording_data(
    session_id: str,
    video_path: str, current_user: CurrentUserOptional = None):
    """Preview recording data (debug) — returns keyframe plan without calling LLM."""
    from app.infrastructure.video.compressor import KeyframeSelector

    try:
        synthesizer = MultimodalSkillSynthesizer()
        video_info = await synthesizer._get_video_info(video_path)
        events = await synthesizer._fetch_events(session_id)

        selector = KeyframeSelector()
        keyframes = selector.select_keyframes(events=events, video_duration=video_info.duration)

        return PreviewRecordingDataResponse(
            video_info=PreviewVideoInfo(
                path=video_path,
                duration=video_info.duration,
                resolution=f"{video_info.width}x{video_info.height}",
                fps=video_info.fps,
            ),
            events=PreviewEventsSummary(
                total=len(events),
                types=list(set(e.action_type for e in events)),
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
            )
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"Preview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recordings/{session_id}/annotations", response_model=list[AnnotationResponse])
async def list_annotations(session_id: str, current_user: CurrentUserOptional = None):
    """Get all annotations (region_extract events from TraceEvent)."""
    async with session_scope() as db:
        stmt = select(TraceEvent).where(TraceEvent.member_id == (current_user.id if current_user else 0)).where(
            TraceEvent.recording_session_id == session_id,
            TraceEvent.action_type == "region_extract"
        ).order_by(TraceEvent.timestamp)

        result = await db.execute(stmt)
        events = result.scalars().all()

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
                    } if coords else None,
                    user_note=e.target_text or "Screen region extraction",
                    created_at=e.created_at if e.created_at else datetime.now(),
                )
            )

        return annotations


@router.post("/recordings/{session_id}/smart-synthesis", response_model=SmartSynthesisResponse)
async def start_smart_synthesis(
    session_id: str,
    body: SmartSynthesisRequest,
    background_tasks: BackgroundTasks, current_user: CurrentUserOptional = None):
    """Start an async smart synthesis job."""
    async with session_scope() as db:
        if body.annotation_ids:
            stmt = select(TraceEvent).where(TraceEvent.member_id == (current_user.id if current_user else 0)).where(
                TraceEvent.id.in_(body.annotation_ids),
                TraceEvent.action_type == "region_extract"
            )
        else:
            stmt = select(TraceEvent).where(TraceEvent.member_id == (current_user.id if current_user else 0)).where(
                TraceEvent.recording_session_id == session_id,
                TraceEvent.action_type == "region_extract"
            )

        result = await db.execute(stmt)
        annotations = result.scalars().all()

        if not annotations:
            raise HTTPException(status_code=400, detail="No annotations found for synthesis")

        job = SynthesisJob(member_id=current_user.id if current_user else 0,
            session_id=session_id,
            thread_id=body.thread_id,
            task_goal=body.task_goal,
            annotation_ids=[a.id for a in annotations],
            status="pending",
            progress_percent=0,
        )
        db.add(job)
        await db.flush()
        await db.refresh(job)

        background_tasks.add_task(
            _run_smart_synthesis,
            job_id=job.id,
            session_id=session_id,
            thread_id=body.thread_id,
            task_goal=body.task_goal,
            annotation_ids=[a.id for a in annotations],
            current_user=current_user,
        )

        return SmartSynthesisResponse(
            job_id=job.id,
            status="pending",
            message=f"Synthesis job started with {len(annotations)} annotations",
        )


async def _run_smart_synthesis(
    job_id: int,
    session_id: str,
    thread_id: str | None,
    task_goal: str,
    annotation_ids: list[int],
    current_user: CurrentUserOptional = None,
):
    """Background smart synthesis worker."""
    from app.core.learning.smart_synthesizer import SmartSynthesizer

    async with session_scope() as db:
        stmt = select(SynthesisJob).where(SynthesisJob.member_id == (current_user.id if current_user else 0)).where(SynthesisJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one()
        job.status = "processing"
        job.started_at = datetime.now()
        await db.commit()

    try:
        async with session_scope() as db:
            stmt = select(TraceEvent).where(TraceEvent.member_id == (current_user.id if current_user else 0)).where(
                TraceEvent.id.in_(annotation_ids),
                TraceEvent.action_type == "region_extract"
            )
            result = await db.execute(stmt)
            annotations = result.scalars().all()

        synthesizer = SmartSynthesizer(
            job_id=job_id, session_id=session_id, thread_id=thread_id,
            task_goal=task_goal, annotations=list(annotations),
        )

        skill = await synthesizer.synthesize()

        async with session_scope() as db:
            stmt = select(SynthesisJob).where(SynthesisJob.member_id == (current_user.id if current_user else 0)).where(SynthesisJob.id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one()

            job.status = "completed"
            job.progress_percent = 100
            job.completed_at = datetime.now()
            skill_dict = skill if isinstance(skill, dict) else {
                "name": getattr(skill, 'name', 'unnamed_skill'),
                "description": getattr(skill, 'description', ''),
                "namespace": getattr(skill, 'namespace', 'misc'),
                "trigger_patterns": getattr(skill, 'trigger_patterns', []),
                "instructions": getattr(skill, 'instructions', ''),
                "execution_mode": getattr(skill, 'execution_mode', 'agentic'),
                "macro_script": getattr(skill, 'macro_script', ''),
            }
            job.generated_skill = skill_dict

            try:
                new_skill = LearnedSkill(member_id=current_user.id if current_user else 0,
                    name=skill_dict.get("name", "unnamed_skill"),
                    description=skill_dict.get("description", ""),
                    namespace=skill_dict.get("namespace", "misc"),
                    trigger_patterns=json.dumps(skill_dict.get("trigger_patterns", [])),
                    parameters="[]",
                    instructions=skill_dict.get("instructions", ""),
                    execution_mode=skill_dict.get("execution_mode", "agentic"),
                    macro_script=skill_dict.get("macro_script", ""),
                    is_active=False,
                    status="pending_review",
                    skill_source="smart_replay",
                )
                db.add(new_skill)
                await db.flush()
                job.skill_id = new_skill.id
                logger.info(f"[Job {job_id}] Saved skill to LearnedSkill: {new_skill.id} - {skill_dict.get('name')}")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning(f"[Job {job_id}] Failed to save skill to LearnedSkill: {e}")

            await db.commit()

        try:
            from app.core.learning.event.publishers import publish_synthesis_completed
            await publish_synthesis_completed(job_id=job_id, status="completed", skill_id=job.skill_id, session_id=session_id)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning(f"[Job {job_id}] Failed to publish synthesis completed event: {e}")

    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"Smart synthesis failed for job {job_id}: {e}")

        async with session_scope() as db:
            stmt = select(SynthesisJob).where(SynthesisJob.member_id == (current_user.id if current_user else 0)).where(SynthesisJob.id == job_id)
            result = await db.execute(stmt)
            job = result.scalar_one()

            job.status = "failed"
            job.error_message = str(e)
            job.error_traceback = traceback.format_exc()
            job.completed_at = datetime.now()
            await db.commit()

        try:
            from app.core.learning.event.publishers import publish_synthesis_completed
            await publish_synthesis_completed(job_id=job_id, status="failed", session_id=session_id)
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as pub_e:
            logger.warning(f"[Job {job_id}] Failed to publish synthesis failed event: {pub_e}")


@router.get("/synthesis-jobs/{job_id}", response_model=SynthesisJobResponse)
async def get_synthesis_job(job_id: int, current_user: CurrentUserOptional = None):
    """Get synthesis job status and results."""
    async with session_scope() as db:
        stmt = select(SynthesisJob).where(SynthesisJob.member_id == (current_user.id if current_user else 0)).where(SynthesisJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(status_code=404, detail="Synthesis job not found")

        return SynthesisJobResponse(
            id=job.id,
            session_id=job.session_id,
            status=job.status,
            progress_percent=job.progress_percent,
            current_phase=job.current_phase,
            task_goal=job.task_goal,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            result={"skill": job.generated_skill, "insights": job.extracted_insights} if job.generated_skill else None,
            error={"message": job.error_message, "traceback": job.error_traceback} if job.error_message else None,
        )


@router.get("/recordings/{session_id}/synthesis-jobs", response_model=list[SynthesisJobResponse])
async def list_session_synthesis_jobs(session_id: str, current_user: CurrentUserOptional = None):
    """Get all synthesis jobs for a recording session."""
    async with session_scope() as db:
        stmt = select(SynthesisJob).where(SynthesisJob.member_id == (current_user.id if current_user else 0)).where(
            SynthesisJob.session_id == session_id
        ).order_by(SynthesisJob.created_at.desc())

        result = await db.execute(stmt)
        jobs = result.scalars().all()

        return [
            SynthesisJobResponse(
                id=j.id,
                session_id=j.session_id,
                status=j.status,
                progress_percent=j.progress_percent,
                current_phase=j.current_phase,
                task_goal=j.task_goal,
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
                result={"skill": j.generated_skill} if j.generated_skill else None,
                error={"message": j.error_message} if j.error_message else None,
            )
            for j in jobs
        ]


@router.delete("/recordings/{session_id}", response_model=CleanupRecordingResponse)
async def cleanup_recording_session(
    session_id: str,
    video_path: str | None = None, current_user: CurrentUserOptional = None):
    """Clean up all data associated with a recording session."""
    deleted_counts = {"events": 0, "jobs": 0, "video_file": False}

    try:
        async with session_scope() as db:
            stmt = delete(TraceEvent).where(TraceEvent.member_id == (current_user.id if current_user else 0)).where(
                or_(TraceEvent.recording_session_id == session_id, TraceEvent.session_id == session_id)
            )
            result = await db.execute(stmt)
            deleted_counts["events"] = getattr(result, "rowcount", 0)

            stmt = delete(SynthesisJob).where(SynthesisJob.member_id == (current_user.id if current_user else 0)).where(SynthesisJob.session_id == session_id)
            result = await db.execute(stmt)
            deleted_counts["jobs"] = getattr(result, "rowcount", 0)

        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                deleted_counts["video_file"] = True
                logger.info(f"[Cleanup] Deleted video file: {video_path}")
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[Cleanup] Failed to delete video file {video_path}: {e}")

        logger.info(f"[Cleanup] Session {session_id} cleaned up: {deleted_counts}")

        return CleanupRecordingResponse(
            success=True,
            message=f"Recording session {session_id} cleaned up",
            deleted=deleted_counts,
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.exception(f"[Cleanup] Failed to cleanup session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
