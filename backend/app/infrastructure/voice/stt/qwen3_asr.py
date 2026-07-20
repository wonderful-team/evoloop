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

# sherpa_onnx 延迟导入检查
try:
    import sherpa_onnx
    SHERPA_ONNX_AVAILABLE = True
except ImportError:
    SHERPA_ONNX_AVAILABLE = False


def _get_bundled_qwen3_models_path() -> Path | None:
    """获取应用 bundle 或本地存储中的 Qwen3-ASR 模型路径"""
    models_dir = getattr(settings, "MODELS_DIR", None) or os.path.expanduser("~/.evoloop/models")
    base_path = Path(models_dir)

    # 1. 尝试 ~/.evoloop/models/qwen3-asr
    qwen3_dir = base_path / "qwen3-asr"
    if qwen3_dir.exists() and (qwen3_dir / "encoder.int8.onnx").exists():
        return qwen3_dir

    # 2. 尝试匹配 ~/.evoloop/models/ 目录下的 sherpa-onnx-qwen3-asr-* 子路径
    if base_path.exists():
        for sub in base_path.iterdir():
            if sub.is_dir() and "qwen3" in sub.name.lower():
                if (sub / "encoder.int8.onnx").exists() or (sub / "encoder.onnx").exists():
                    return sub

    tauri_dir = getattr(settings, "TAURI_RESOURCE_DIR", None)
    if tauri_dir:
        bundle_models = Path(tauri_dir) / "models" / "qwen3-asr"
        if bundle_models.exists():
            return bundle_models

    cwd_models = Path.cwd() / "models" / "qwen3-asr"
    if cwd_models.exists():
        return cwd_models

    return None


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
    except Exception:
        pass

    # 尝试 2: 调用 ffmpeg 将任意格式 (webm/mp3/m4a/wav) 转码为 16kHz s16le PCM 流
    try:
        cmd = [
            "ffmpeg", "-loglevel", "quiet", "-y", "-i", file_path,
            "-f", "s16le", "-ac", "1", "-ar", "16000", "-"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        raw_int16 = array.array("h", res.stdout)
        return [s / 32768.0 for s in raw_int16]
    except Exception as e:
        logger.warning(f"[Qwen3ASR] ffmpeg transcode failed: {e}")

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
        db_model_dir = SystemConfigService.get_value("QWEN3_ASR_MODEL_DIR")
        models_dir = getattr(settings, "MODELS_DIR", None) or os.path.expanduser("~/.evoloop/models")
        
        if model_dir:
            self.model_dir = Path(model_dir)
        elif db_model_dir:
            self.model_dir = Path(db_model_dir)
        else:
            bundled = _get_bundled_qwen3_models_path()
            self.model_dir = bundled if bundled else Path(models_dir) / "qwen3-asr"

        self._recognizer = None
        self._load_lock = asyncio.Lock()

    def is_available(self) -> bool:
        """检查 sherpa-onnx 依赖及 Qwen3-ASR 模型文件"""
        if not SHERPA_ONNX_AVAILABLE:
            return False
        encoder_int8 = self.model_dir / "encoder.int8.onnx"
        encoder_fp32 = self.model_dir / "encoder.onnx"
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

            conv_frontend = str(self.model_dir / "conv_frontend.onnx")
            encoder_int8 = self.model_dir / "encoder.int8.onnx"
            encoder = str(encoder_int8 if encoder_int8.exists() else self.model_dir / "encoder.onnx")
            decoder_int8 = self.model_dir / "decoder.int8.onnx"
            decoder = str(decoder_int8 if decoder_int8.exists() else self.model_dir / "decoder.onnx")
            tokenizer = str(self.model_dir / "tokenizer")

            if not os.path.exists(encoder):
                raise RuntimeError(f"Qwen3-ASR model not found at {self.model_dir}")

            logger.info(f"[Qwen3ASR] Loading model from {self.model_dir}...")
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
            logger.info(f"[Qwen3ASR] Model loaded successfully from {self.model_dir}")

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
            logger.error(f"[Qwen3ASR] Transcription failed: {e}")
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
