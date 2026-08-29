"""
Qwen3-ASR Provider for Backend STT
Qwen3-ASR 本地语音识别提供商（基于 sherpa-onnx）
"""

import array
import asyncio
import logging
import os
import subprocess
import tempfile
import wave
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.config import settings
from app.infrastructure.voice.stt.base import (
    BaseSTTProvider,
    STTOptions,
    STTResult,
    VoiceLocale,
)

logger = logging.getLogger(__name__)


def _ensure_sherpa_onnx_runtime() -> None:
    """
    处理 sherpa-onnx wheel 在 macOS 上未打包 onnxruntime dylib 的问题。
    如果 sherpa_onnx/lib 缺少对应的 libonnxruntime，则尝试从已安装的 onnxruntime
    包中创建符号链接作为临时兼容方案。
    """
    # 先找到 sherpa_onnx 包目录，不直接导入它（导入可能因缺少 dylib 失败）
    import importlib.util

    spec = importlib.util.find_spec("sherpa_onnx")
    if not spec or not spec.origin:
        return

    sherpa_dir = Path(spec.origin).parent / "lib"
    if not sherpa_dir.exists():
        return

    # 找到已安装的 onnxruntime 动态库
    try:
        import onnxruntime
    except ImportError:
        return

    onnx_dir = Path(onnxruntime.__file__).parent / "capi"
    if not onnx_dir.exists():
        return

    # macOS 用 dylib，Linux 用 so，Windows 用 dll
    sysname = getattr(os.uname(), "sysname", "") if hasattr(os, "uname") else ""
    if os.name == "posix" and sysname == "Darwin":
        ext = ".dylib"
    elif os.name == "posix":
        ext = ".so"
    else:
        ext = ".dll"

    onnx_libs = sorted([p for p in onnx_dir.glob(f"libonnxruntime*{ext}*") if p.is_file()])
    if not onnx_libs:
        return

    for onnx_lib in onnx_libs:
        target = sherpa_dir / onnx_lib.name
        if target.exists() or target.is_symlink():
            continue
        try:
            os.symlink(onnx_lib, target)
            logger.info(f"[Qwen3ASR] Linked {onnx_lib} -> {target}")
        except OSError:
            pass


# 在导入 sherpa_onnx 之前尝试修复动态库依赖
_ensure_sherpa_onnx_runtime()

# sherpa_onnx 延迟导入检查
try:
    import sherpa_onnx

    SHERPA_ONNX_AVAILABLE = True
except ImportError:
    SHERPA_ONNX_AVAILABLE = False


def _get_qwen3_search_dirs() -> list[Path]:
    """Return directories to search for the Qwen3-ASR model.

    Order: bundled models (via MODELS_DIR env) → user downloads → legacy paths.
    """
    dirs: list[Path] = []

    models_dir = getattr(settings, "MODELS_DIR", None)
    if models_dir:
        dirs.append(Path(models_dir))

    dirs.append(Path(os.path.expanduser("~/.evoloop/models")))

    tauri_dir = getattr(settings, "TAURI_RESOURCE_DIR", None)
    if tauri_dir:
        dirs.append(Path(tauri_dir) / "models")

    cwd_models = Path.cwd() / "models"
    if cwd_models not in dirs:
        dirs.append(cwd_models)

    return dirs


def _find_qwen3_model_dir() -> Path | None:
    """Search known locations for a Qwen3-ASR model directory."""
    for base_path in _get_qwen3_search_dirs():
        # 1. Direct qwen3-asr subdirectory
        qwen3_dir = base_path / "qwen3-asr"
        if qwen3_dir.exists() and (qwen3_dir / "encoder.int8.onnx").exists():
            return qwen3_dir

        # 2. Any sherpa-onnx-qwen3-asr-* subdirectory
        if base_path.exists():
            for sub in base_path.iterdir():
                if sub.is_dir() and "qwen3" in sub.name.lower():
                    if (sub / "encoder.int8.onnx").exists() or (sub / "encoder.onnx").exists():
                        return sub

    return None


def _get_default_qwen3_dir() -> Path:
    """Default directory to use when no Qwen3-ASR model has been found yet.

    We prefer the user-writable location so that a model downloaded later via
    the frontend becomes available without recreating the provider.
    """
    return Path(os.path.expanduser("~/.evoloop/models")) / "qwen3-asr"


def _load_audio_samples_16k(file_path: str) -> list[float]:
    """读取或转换音频文件为 16kHz 单声道 f32 浮点数组"""
    # 尝试 1: 原生 wave 模块 (支持 16kHz PCM wav)
    try:
        with wave.open(file_path, "rb") as wf:
            num_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            num_frames = wf.getnframes()
            frames = wf.readframes(num_frames)

            if sample_width == 2 and framerate == 16000:
                raw_int16 = array.array("h", frames)
                if num_channels > 1:
                    raw_int16 = raw_int16[::num_channels]
                return [s / 32768.0 for s in raw_int16]
    except (wave.Error, EOFError, OSError, ValueError):
        logger.debug("[Qwen3ASR] wave read failed, trying ffmpeg", exc_info=True)

    # 尝试 2: 调用 ffmpeg 将任意格式 (webm/mp3/m4a/wav) 转码为 16kHz s16le PCM 流
    try:
        cmd = [
            "ffmpeg", "-loglevel", "quiet", "-y", "-i", file_path,
            "-f", "s16le", "-ac", "1", "-ar", "16000", "-",
        ]
        res = subprocess.run(cmd, capture_output=True, check=True)
        raw_int16 = array.array("h", res.stdout)
        return [s / 32768.0 for s in raw_int16]
    except Exception as e:
        logger.warning(f"[Qwen3ASR] ffmpeg transcode failed: {e}", exc_info=True)

    raise ValueError(f"Unable to read or convert audio file: {file_path}")


class Qwen3ASRProvider(BaseSTTProvider):
    """
    Qwen3-ASR 本地语音识别提供商
    与 Tauri 桌面端原生引擎保持一致，基于 sherpa-onnx 离线识别。
    """

    name = "qwen3-asr"
    supports_streaming = False
    supports_timestamps = False

    def __init__(self, model_dir: str | None = None):
        from app.infrastructure.config.service import SystemConfigService

        self._explicit_model_dir: Path | None = None
        if model_dir:
            self._explicit_model_dir = Path(model_dir)
        else:
            db_model_dir = SystemConfigService.get_value("QWEN3_ASR_MODEL_DIR")
            if db_model_dir:
                self._explicit_model_dir = Path(db_model_dir)

        self.model_dir: Path = self._resolve_model_dir()
        self._recognizer = None
        self._load_lock = asyncio.Lock()

    def _resolve_model_dir(self) -> Path:
        """Return the effective model directory, scanning all known locations."""
        if self._explicit_model_dir:
            return self._explicit_model_dir
        found = _find_qwen3_model_dir()
        return found if found else _get_default_qwen3_dir()

    def is_available(self) -> bool:
        """检查 sherpa-onnx 依赖及 Qwen3-ASR 模型文件"""
        if not SHERPA_ONNX_AVAILABLE:
            return False
        model_dir = self._resolve_model_dir()
        encoder_int8 = model_dir / "encoder.int8.onnx"
        encoder_fp32 = model_dir / "encoder.onnx"
        return encoder_int8.exists() or encoder_fp32.exists()

    async def _load_recognizer(self):
        """线程安全的模型加载逻辑"""
        if self._recognizer is not None:
            return

        async with self._load_lock:
            if self._recognizer is not None:
                return

            if not SHERPA_ONNX_AVAILABLE:
                raise RuntimeError("sherpa-onnx dependency missing. Please install sherpa-onnx.")

            model_dir = self._resolve_model_dir()
            self.model_dir = model_dir

            conv_frontend = str(model_dir / "conv_frontend.onnx")
            encoder_int8 = model_dir / "encoder.int8.onnx"
            encoder = str(encoder_int8 if encoder_int8.exists() else model_dir / "encoder.onnx")
            decoder_int8 = model_dir / "decoder.int8.onnx"
            decoder = str(decoder_int8 if decoder_int8.exists() else model_dir / "decoder.onnx")
            tokenizer = str(model_dir / "tokenizer")

            if not os.path.exists(encoder):
                raise RuntimeError(f"Qwen3-ASR model not found at {model_dir}")

            logger.info(f"[Qwen3ASR] Loading model from {model_dir}...")
            loop = asyncio.get_running_loop()

            def _create():
                recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
                    conv_frontend=conv_frontend,
                    encoder=encoder,
                    decoder=decoder,
                    tokenizer=tokenizer,
                    num_threads=4,
                )
                if not recognizer:
                    raise RuntimeError("Failed to create sherpa_onnx OfflineRecognizer (Qwen3-ASR)")
                return recognizer

            self._recognizer = await loop.run_in_executor(None, _create)
            logger.info(f"[Qwen3ASR] Model loaded successfully from {model_dir}")

    def list_models(self, language: VoiceLocale | None = None) -> list[str]:
        return ["qwen3-asr-int8"]

    async def transcribe(self, options: STTOptions) -> STTResult:
        await self._load_recognizer()

        # 处理音频输入路径或字节
        if options.file_path and os.path.exists(options.file_path):
            tmp_path = options.file_path
            is_temporary = False
        else:
            if not options.audio_data:
                raise ValueError("Missing audio data or file path")

            suffix = f".{options.audio_format}" if options.audio_format else ".wav"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(options.audio_data)
                tmp_path = tmp.name
            is_temporary = True

        try:
            loop = asyncio.get_running_loop()
            samples = await loop.run_in_executor(None, lambda: _load_audio_samples_16k(tmp_path))

            def _decode():
                stream = self._recognizer.create_stream()
                stream.accept_waveform(16000, samples)
                self._recognizer.decode_stream(stream)
                return stream.result.text.strip()

            text = await loop.run_in_executor(None, _decode)
            return STTResult(
                text=text,
                language=VoiceLocale.ZH_CN,
            )
        except Exception as e:
            logger.exception(f"[Qwen3ASR] Transcription failed: {e}")
            raise
        finally:
            if is_temporary:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        async def _gen():
            result = await self.transcribe(options)
            yield result

        return _gen()
