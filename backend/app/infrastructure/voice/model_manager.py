"""
Model Manager — download and track optional local model availability.

Models:
  - qwen3_asr:     Qwen3-ASR via sherpa-onnx (954MB)
  - bge-base-zh-v1.5: Local text embedding model (GGUF, ~61MB)
"""

import asyncio
import logging
import os
import requests
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# HuggingFace-compatible endpoint used for direct URL downloads (e.g. bge GGUF).
# The bundled config (HF_ENDPOINT) defaults to a mirror; it can be overridden
# via the HF_ENDPOINT environment variable.
_HF_ENDPOINT = settings.HF_ENDPOINT.rstrip("/")


# Model definitions
MODEL_DEFS: dict[str, dict[str, Any]] = {
    "qwen3_asr": {
        "name": "Qwen3-ASR",
        "size_gb": 0.954,
        "size_label": "954MB",
        "total_bytes": 954_000_000,
        "sub_dir": "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
        "check_file": "encoder.int8.onnx",
        "source": "modelscope",
        "source_id": "jkman2023/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
        "url": None,
    },
    "bge-base-zh-v1.5": {
        "name": "BGE-Base-Zh-v1.5",
        "size_gb": 0.061,
        "size_label": "61MB",
        "total_bytes": 64_000_000,
        "sub_dir": "gguf",
        "check_file": "bge-base-zh-v1.5-q4_k_m.gguf",
        "source": "url",
        "source_id": None,
        "url": (
            f"{_HF_ENDPOINT}/CompendiumLabs/bge-base-zh-v1.5-gguf/"
            "resolve/main/bge-base-zh-v1.5-q4_k_m.gguf"
        ),
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


def _get_dir_size(path: str) -> float:
    """Get total size of all files in a directory tree, in bytes."""
    total = 0.0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


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

        # If the model is already on disk, treat it as completed unless an active
        # download is in progress. This prevents a stale "failed" status from
        # masking an otherwise available model.
        status = progress.status
        if downloaded and status != "downloading":
            status = "completed"

        return {
            "id": model_id,
            "name": model_def["name"],
            "size": model_def["size_label"],
            "size_gb": model_def["size_gb"],
            "downloaded": downloaded,
            "available": downloaded,
            "status": status,
            "progress": progress.progress if status == "downloading" else None,
        }

    def get_all_status(self) -> list[dict[str, Any]]:
        return [self.get_status(mid) for mid in MODEL_DEFS]

    @staticmethod
    def _get_models_dir() -> str:
        """User-writable directory for optional model downloads.

        Core models (classifiers, KWS) are bundled with the app and loaded via
        the MODELS_DIR environment variable. Optional downloads always go to the
        user's home directory so the app bundle stays read-only.
        """
        return os.path.expanduser("~/.evoloop/models")

    def _check_downloaded(self, model_id: str) -> bool:
        model_def = MODEL_DEFS.get(model_id)
        if not model_def:
            return False
        sub_dir = model_def.get("sub_dir")
        check_file = model_def.get("check_file")
        if sub_dir:
            expected = os.path.join(self._get_models_dir(), sub_dir)
            if check_file:
                if os.path.isfile(os.path.join(expected, check_file)):
                    return True
            elif os.path.isdir(expected) and bool(os.listdir(expected)):
                return True
        # For huggingface models, also check HF cache
        src = model_def.get("source_id")
        if src:
            # Check unified models HF cache first, then fallback to global cache
            hf_cache_root = os.path.join(self._get_models_dir(), ".cache", "huggingface")
            hf_dir = os.path.join(hf_cache_root, "hub", f"models--{src.replace('/', '--')}", "snapshots")
            if not os.path.isdir(hf_dir):
                hf_dir = os.path.join(
                    os.path.expanduser("~/.cache/huggingface/hub"),
                    f"models--{src.replace('/', '--')}",
                    "snapshots",
                )

            if os.path.isdir(hf_dir):
                for s in os.listdir(hf_dir):
                    sp = os.path.join(hf_dir, s)
                    if os.path.isdir(sp) and bool(os.listdir(sp)):
                        return True
        return False

    async def start_download(self, model_id: str) -> None:
        if self._check_downloaded(model_id):
            self._progress[model_id] = DownloadProgress(model_id=model_id, progress=1.0, status="completed")
            return

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
            elif model_def["source"] == "huggingface":
                await self._download_from_huggingface(model_id, model_def)
            elif model_def["source"] == "url":
                await self._download_from_url(model_id, model_def)
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
            shutil.rmtree(target_dir)

        # Estimate total download size for progress tracking
        total_bytes: float = model_def.get("total_bytes", model_def["size_gb"] * 1_000_000_000)

        async def _track_progress():
            """Periodically check directory size to estimate download progress."""
            while True:
                await asyncio.sleep(2)
                size = _get_dir_size(target_dir)
                p = min(size / total_bytes, 0.99)
                self._progress[model_id] = DownloadProgress(
                    model_id=model_id, status="downloading", progress=p
                )
                if os.path.isfile(target_path):
                    return

        def _do_snapshot():
            os.makedirs(self._get_models_dir(), exist_ok=True)
            snapshot_download(source_id, local_dir=target_dir)

        loop = asyncio.get_running_loop()
        # Start progress tracker in background
        tracker = asyncio.create_task(_track_progress())
        try:
            await loop.run_in_executor(None, _do_snapshot)
        finally:
            tracker.cancel()

        if target_path and os.path.isfile(target_path):
            self._progress[model_id] = DownloadProgress(
                model_id=model_id, progress=1.0, status="completed"
            )
        else:
            self._fail(model_id, f"Download completed but {check_file} not found")

    async def _download_from_huggingface(self, model_id: str, model_def: dict) -> None:
        from huggingface_hub import snapshot_download as hf_sd

        src = model_def["source_id"]
        total = model_def.get("total_bytes", model_def["size_gb"] * 1_000_000_000)
        hf_cache_root = os.path.join(self._get_models_dir(), ".cache", "huggingface")
        hf_cache = os.path.join(hf_cache_root, "hub", f"models--{src.replace('/', '--')}")

        async def _track():
            while True:
                await asyncio.sleep(2)
                sz = _get_dir_size(hf_cache)
                self._progress[model_id] = DownloadProgress(
                    model_id=model_id,
                    status="downloading",
                    progress=min(sz / total, 0.99),
                )

        def _do():
            hf_sd(src)

        loop = asyncio.get_running_loop()
        t = asyncio.create_task(_track())
        try:
            await loop.run_in_executor(None, _do)
        finally:
            t.cancel()
        self._progress[model_id] = DownloadProgress(model_id=model_id, progress=1.0, status="completed")

    async def _download_from_url(self, model_id: str, model_def: dict) -> None:
        url = model_def.get("url")
        if not url:
            self._fail(model_id, "No URL configured for url source")
            return

        target_dir = os.path.join(self._get_models_dir(), model_def["sub_dir"])
        filename = model_def.get("check_file") or url.rstrip("/").rsplit("/", 1)[-1]
        target_path = os.path.join(target_dir, filename)
        total = model_def.get("total_bytes", model_def["size_gb"] * 1_000_000_000)

        if os.path.exists(target_path):
            os.remove(target_path)

        async def _track():
            while True:
                await asyncio.sleep(1)
                if os.path.isfile(target_path):
                    sz = os.path.getsize(target_path)
                    self._progress[model_id] = DownloadProgress(
                        model_id=model_id,
                        status="downloading",
                        progress=min(sz / total, 0.99),
                    )
                if self._progress.get(model_id, DownloadProgress(model_id=model_id)).status in ("completed", "failed"):
                    return

        def _do_download():
            os.makedirs(target_dir, exist_ok=True)
            logger.info(f"[ModelManager] Downloading {model_id} from {url}")
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                        if chunk:
                            f.write(chunk)

        loop = asyncio.get_running_loop()
        t = asyncio.create_task(_track())
        try:
            await loop.run_in_executor(None, _do_download)
        finally:
            t.cancel()

        if os.path.isfile(target_path):
            self._progress[model_id] = DownloadProgress(model_id=model_id, progress=1.0, status="completed")
        else:
            self._fail(model_id, f"Download completed but {target_path} not found")

    def _fail(self, model_id: str, error: str) -> None:
        self._progress[model_id] = DownloadProgress(model_id=model_id, status="failed", error=error)

    async def wait_for_progress(self, model_id: str) -> AsyncIterator[DownloadProgress]:
        """Yield progress updates as they happen (for SSE streaming)."""
        while True:
            prog = self._progress.get(model_id, DownloadProgress(model_id=model_id))
            yield prog
            if prog.status in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)


# Module singleton
model_manager = ModelManager()
