import asyncio
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.config import settings
from app.infrastructure.voice.stt.base import BaseSTTProvider, STTOptions, STTResult, VoiceLocale

logger = logging.getLogger(__name__)

# FunASR 模型配置
FUNASR_MODELS = {
    "paraformer-zh": {
        "model_id": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "description": "基础模型，通用场景",
        "size": "~220MB",
        "language": "zh",
    },
    "paraformer-zh-plus": {
        "model_id": "damo/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "description": "增强模型，带 VAD 和标点",
        "size": "~500MB",
        "language": "zh",
    },
    "paraformer-zh-streaming": {
        "model_id": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
        "description": "流式模型，实时识别",
        "size": "~220MB",
        "language": "zh",
    },
    "paraformer-zh-en": {
        "model_id": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "description": "中英混合模型",
        "size": "~220MB",
        "language": "zh-en",
    },
}


def _get_bundled_models_path() -> Path | None:
    """获取应用 bundle 中的模型路径"""
    if getattr(settings, 'TAURI_RESOURCE_DIR', None):
        bundle_models = Path(settings.TAURI_RESOURCE_DIR) / "models"
        if bundle_models.exists():
            return bundle_models

    if getattr(sys, 'frozen', False):
        bundle_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
        bundle_models = bundle_dir / "models"
        if bundle_models.exists():
            return bundle_models

    cwd_models = Path.cwd() / "models"
    if cwd_models.exists():
        return cwd_models

    return None


def _copy_bundled_models_if_needed():
    """鲁棒的模型同步逻辑：从应用 bundle 复制到用户目录"""
    bundled_path = _get_bundled_models_path()
    if not bundled_path:
        return

    user_models_dir = Path(settings.MODELS_DIR)

    # 检查是否已存在（快速校验）
    if user_models_dir.exists() and any(user_models_dir.iterdir()):
        logger.debug(f"Models already exist in {user_models_dir}, skipping sync")
        return

    logger.info(f"Syncing bundled models from {bundled_path} to {user_models_dir}")

    try:
        user_models_dir.mkdir(parents=True, exist_ok=True)
        for item in bundled_path.iterdir():
            dest = user_models_dir / item.name
            
            # 安全清理冲突路径
            if dest.exists():
                if dest.is_dir() and not dest.is_symlink():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            
            if item.is_dir():
                shutil.copytree(item, dest)
                logger.info(f"Deployed model directory: {item.name}")
            else:
                shutil.copy2(item, dest)
                logger.info(f"Deployed model file: {item.name}")

        logger.info("Bundled models deployment complete")
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Model deployment warning: {e}")


class FunASRProvider(BaseSTTProvider):
    """
    FunASR 本地语音识别提供商（工程强化版）
    """

    name = "funasr"
    supports_streaming = True
    supports_timestamps = True

    def __init__(self, model_name: str | None = None):
        from app.infrastructure.config import SystemConfigService
        self.model_name = model_name or SystemConfigService.get_value("FUNASR_MODEL") or settings.FUNASR_MODEL
        self.device = SystemConfigService.get_value("FUNASR_DEVICE") or settings.FUNASR_DEVICE
        self._model = None
        self._load_lock = asyncio.Lock()
        self._funasr_available = self._check_dependencies()

    def _check_dependencies(self) -> bool:
        """检查依赖是否安装"""
        try:
            import funasr
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        return self._funasr_available

    async def _load_model(self):
        """线程安全的模型加载逻辑"""
        if self._model is not None:
            return

        async with self._load_lock:
            # 双重检查
            if self._model is not None:
                return

            if not self._funasr_available:
                raise RuntimeError("FunASR dependencies missing. Please install funasr, modelscope, torch.")

            # 延迟设置环境变量，避免副作用
            os.environ["MODELSCOPE_CACHE"] = settings.MODELS_DIR
            _copy_bundled_models_if_needed()

            try:
                from funasr import AutoModel
                model_config = FUNASR_MODELS.get(self.model_name, FUNASR_MODELS["paraformer-zh"])
                model_id = model_config["model_id"]

                logger.info(f"[FunASR] Loading model '{self.model_name}' on {self.device}...")
                
                # 运行在执行器中，防止阻塞主线程
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(
                    None,
                    lambda: AutoModel(
                        model=model_id,
                        model_revision="v2.0.4",
                        device=self.device,
                    )
                )
                logger.info(f"[FunASR] Model loaded successfully: {self.model_name}")

            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"[FunASR] Critical load error: {e}")
                raise RuntimeError(f"Failed to load FunASR model: {e}")

    def list_models(self, language: VoiceLocale | None = None) -> list[str]:
        if language:
            lang_map = {
                VoiceLocale.ZH_CN: ["paraformer-zh", "paraformer-zh-plus", "paraformer-zh-streaming", "paraformer-zh-en"],
                VoiceLocale.EN_US: ["paraformer-zh-en"],
                VoiceLocale.AUTO: list(FUNASR_MODELS.keys()),
            }
            return lang_map.get(language, list(FUNASR_MODELS.keys()))
        return list(FUNASR_MODELS.keys())

    async def transcribe(self, options: STTOptions) -> STTResult:
        await self._load_model()

        # 路径透传优化 (Zero-Copy)
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
            result = await loop.run_in_executor(
                None,
                lambda: self._model.generate(input=tmp_path, batch_size=1)
            )

            # 深度结果解析
            if result and len(result) > 0:
                raw_item = result[0]
                text = raw_item.get("text", "").strip()
                
                # 尝试提取更多元数据
                confidence = raw_item.get("confidence")
                # 某些模型可能在不同的 key 下返回
                if confidence is None and "score" in raw_item:
                    confidence = raw_item.get("score")

                return STTResult(
                    text=text,
                    language=self._detect_language(text),
                    confidence=confidence,
                )
            
            return STTResult(text="", language=options.language or VoiceLocale.AUTO)

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error(f"[FunASR] Transcription failed: {e}")
            raise
        finally:
            if is_temporary:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        """模拟流式识别"""
        async def _gen():
            result = await self.transcribe(options)
            yield result
        return _gen()

    def _detect_language(self, text: str) -> VoiceLocale:
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text.replace(" ", ""))
        if total_chars == 0: return VoiceLocale.ZH_CN
        return VoiceLocale.ZH_CN if (chinese_chars / total_chars) > 0.4 else VoiceLocale.EN_US


import threading


class FunASRManager:
    """
    统一的模型实例管理器 (Unified Manager)
    """

    _instances: dict[str, FunASRProvider] = {}
    _lock = threading.Lock()

    @classmethod
    def get_provider(cls, model_name: str = "paraformer-zh") -> FunASRProvider:
        """单例获取提供商，带线程锁保护"""
        if model_name in cls._instances:
            return cls._instances[model_name]

        with cls._lock:
            if model_name not in cls._instances:
                cls._instances[model_name] = FunASRProvider(model_name)
            return cls._instances[model_name]

    @classmethod
    async def preload_model(cls, model_name: str = "paraformer-zh"):
        provider = cls.get_provider(model_name)
        await provider._load_model()

    @classmethod
    def clear_cache(cls):
        cls._instances.clear()
        logger.info("[FunASRManager] Cache cleared")

    @classmethod
    def get_model_path(cls, model_name: str = "paraformer-zh") -> Path:
        model_config = FUNASR_MODELS.get(model_name, FUNASR_MODELS["paraformer-zh"])
        return Path(settings.MODELS_DIR) / "hub" / model_config["model_id"]

    @classmethod
    def is_model_downloaded(cls, model_name: str = "paraformer-zh") -> bool:
        path = cls.get_model_path(model_name)
        return (path / "model.pt").exists() or (path / "pytorch_model.bin").exists()
