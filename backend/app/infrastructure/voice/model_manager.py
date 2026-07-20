"""
Model Manager — download and track voice model availability.

Models:
  - qwen3_asr:     Qwen3-ASR via sherpa-onnx (954MB)
  - kokoro:        Kokoro-82M TTS (82MB, auto-downloads from HuggingFace)
  - cosyvoice:     CosyVoice-300M-Instruct TTS (2.1GB)
"""

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)



# Model definitions
MODEL_DEFS: dict[str, dict[str, Any]] = {
    "qwen3_asr": {
        "name": "Qwen3-ASR",
        "size_gb": 0.954,
        "size_label": "954MB",
        "sub_dir": "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
        "check_file": "encoder.int8.onnx",
        "source": "modelscope",
        "source_id": "iic/CosyVoice-300M-Instruct",
        "url": None,
    },
    "kokoro": {
        "name": "Kokoro-82M",
        "size_gb": 0.082,
        "size_label": "82MB",
        "sub_dir": None,
        "check_file": None,
        "source": "huggingface",
        "source_id": "hexgrad/Kokoro-82M",
        "url": None,
    },
    "cosyvoice": {
        "name": "CosyVoice-300M",
        "size_gb": 2.1,
        "size_label": "2.1GB",
        "sub_dir": "cosyvoice-300m-instruct",
        "check_file": "llm.pt",
        "source": "modelscope",
        "source_id": "iic/CosyVoice-300M-Instruct",
        "url": None,
    },
}


@dataclass
class DownloadProgress:
    model_id: str = ""
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    status: str = "idle"  # idle | downloading | completed | failed
    error: str = ""


class ModelManager:
    def __init__(self):
        self._progress: dict[str, DownloadProgress] = {}
        self._progress_events: dict[str, asyncio.Event] = {}
        self._download_tasks: dict[str, asyncio.Task] = {}

    def get_status(self, model_id: str) -> dict[str, Any]:
        model_def = MODEL_DEFS.get(model_id)
        if not model_def:
            return {"id": model_id, "error": "unknown model"}

        downloaded = self._check_downloaded(model_id)
        progress = self._progress.get(model_id, DownloadProgress(model_id=model_id))

        return {
            "id": model_id,
            "name": model_def["name"],
            "size": model_def["size_label"],
            "size_gb": model_def["size_gb"],
            "downloaded": downloaded,
            "available": downloaded or model_id == "kokoro",  # kokoro downloads on first use
            "status": progress.status,
            "progress": progress.progress if progress.status == "downloading" else None,
        }

    def get_all_status(self) -> list[dict[str, Any]]:
        return [self.get_status(mid) for mid in MODEL_DEFS]

    @staticmethod
    def _get_models_dir() -> str:
        from app.core.config import settings
        return settings.MODELS_DIR or os.path.expanduser("~/.evoloop/models")

    def _check_downloaded(self, model_id: str) -> bool:
        model_def = MODEL_DEFS.get(model_id)
        if not model_def:
            return False
        sub_dir = model_def.get("sub_dir")
        check_file = model_def.get("check_file")
        if not sub_dir or not check_file:
            return False
        return os.path.isfile(os.path.join(self._get_models_dir(), sub_dir, check_file))

    async def start_download(self, model_id: str) -> None:
        if model_id in self._download_tasks and not self._download_tasks[model_id].done():
            raise RuntimeError(f"Download already in progress for {model_id}")

        self._progress[model_id] = DownloadProgress(model_id=model_id, status="downloading")
        self._progress_events[model_id] = asyncio.Event()

        task = asyncio.create_task(self._do_download(model_id))
        self._download_tasks[model_id] = task

    async def _do_download(self, model_id: str) -> None:
        model_def = MODEL_DEFS.get(model_id)
        if not model_def:
            self._fail(model_id, "Unknown model")
            return

        try:
            if model_def["source"] == "modelscope":
                await self._download_from_modelscope(model_id, model_def)
            else:
                self._fail(model_id, f"Unsupported source: {model_def['source']}")
        except Exception as e:
            logger.exception(f"[ModelManager] Download failed for {model_id}: {e}")
            self._fail(model_id, str(e))

    async def _download_from_modelscope(self, model_id: str, model_def: dict) -> None:
        from modelscope import snapshot_download

        target_dir = os.path.join(self._get_models_dir(), model_def["sub_dir"])
        source_id = model_def["source_id"]

        # We'll track progress via periodic checks of the download dir
        check_file = model_def["check_file"]
        target_path = os.path.join(target_dir, check_file)

        # Remove partial download if exists
        if os.path.exists(target_dir):
            import shutil
            shutil.rmtree(target_dir)

        def _do_snapshot():
            os.makedirs(MODELS_DIR, exist_ok=True)
            snapshot_download(source_id, local_dir=target_dir)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _do_snapshot)

        if os.path.isfile(target_path):
            self._progress[model_id] = DownloadProgress(
                model_id=model_id, progress=1.0, status="completed"
            )
        else:
            self._fail(model_id, f"Download completed but {check_file} not found")

    def _fail(self, model_id: str, error: str) -> None:
        self._progress[model_id] = DownloadProgress(
            model_id=model_id, status="failed", error=error
        )

    async def wait_for_progress(
        self, model_id: str
    ) -> AsyncIterator[DownloadProgress]:
        """Yield progress updates as they happen (for SSE streaming)."""
        while True:
            prog = self._progress.get(model_id, DownloadProgress(model_id=model_id))
            yield prog
            if prog.status in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)


# Module singleton
model_manager = ModelManager()
