"""
Model management API — download status, trigger, progress streaming.
"""

import asyncio
import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.infrastructure.voice.model_manager import model_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])

_ALL_MODEL_IDS = ["qwen3_asr", "kokoro", "cosyvoice"]


class DownloadRequest(BaseModel):
    model_id: str


@router.get("/status")
async def get_model_status(model_id: str | None = None):
    if model_id:
        status = model_manager.get_status(model_id)
        if "error" in status:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content=status)
        return status
    return {"models": model_manager.get_all_status()}


@router.post("/download")
async def start_download(req: DownloadRequest):
    if req.model_id not in _ALL_MODEL_IDS:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={"error": f"Unknown model_id. Valid: {_ALL_MODEL_IDS}"},
        )

    try:
        await model_manager.start_download(req.model_id)
        return {"status": "started", "model_id": req.model_id}
    except RuntimeError as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"error": str(e)})


@router.get("/download/progress")
async def download_progress(model_id: str):
    from fastapi.responses import StreamingResponse

    async def event_stream():
        async for prog in model_manager.wait_for_progress(model_id):
            data = {
                "model_id": prog.model_id,
                "progress": prog.progress,
                "status": prog.status,
                "error": prog.error,
            }
            yield f"data: {json.dumps(data)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
