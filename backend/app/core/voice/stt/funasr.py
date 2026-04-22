"""
FunASR Provider Implementation
阿里巴巴 FunASR 本地语音识别（中文优化，支持离线）

模型说明:
- paraformer-zh: 基础模型，~220MB，适合通用场景
- paraformer-zh-streaming: 流式模型，~220MB，支持实时识别
- paraformer-zh-plus: 增强模型，~500MB，精度更高

模型存储位置: ~/.evoloop/models (可通过 MODELS_DIR 配置)
打包模式: 模型可从应用 bundle 的 resources/models 复制到用户目录
"""

import logging
import os
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.config import settings
from app.core.voice.stt.base import BaseSTTProvider, STTOptions, STTResult, VoiceLocale

logger = logging.getLogger(__name__)

# Ensure ModelScope uses our configured models directory
os.environ["MODELSCOPE_CACHE"] = settings.MODELS_DIR

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
    """
    获取应用 bundle 中的模型路径 (Tauri 打包场景)
    
    Returns:
        Path to bundled models if running from Tauri bundle, None otherwise
    """
    # When running in Tauri, resource_dir is set
    # Try to find models in the resources directory
    if getattr(settings, 'TAURI_RESOURCE_DIR', None):
        bundle_models = Path(settings.TAURI_RESOURCE_DIR) / "models"
        if bundle_models.exists():
            return bundle_models

    # Fallback: Check if running from a PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running in a bundle
        bundle_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
        bundle_models = bundle_dir / "models"
        if bundle_models.exists():
            return bundle_models

    # Check for models in current working directory (development)
    cwd_models = Path.cwd() / "models"
    if cwd_models.exists():
        return cwd_models

    # Check for models in backend resources (src-tauri sidecar mode)
    backend_models = Path(__file__).parent.parent.parent.parent.parent / "src-tauri" / "models"
    if backend_models.exists():
        return backend_models

    return None


def _copy_bundled_models_if_needed():
    """
    如果应用 bundle 中包含模型，复制到用户目录
    这样首次启动时就不需要下载
    """
    bundled_path = _get_bundled_models_path()
    if not bundled_path:
        return

    user_models_dir = Path(settings.MODELS_DIR)

    # Check if models already exist in user directory
    if user_models_dir.exists() and any(user_models_dir.iterdir()):
        logger.debug(f"Models already exist in {user_models_dir}, skipping copy")
        return

    logger.info(f"Found bundled models at {bundled_path}, copying to {user_models_dir}")

    try:
        user_models_dir.mkdir(parents=True, exist_ok=True)

        # Copy all models from bundle to user directory
        for item in bundled_path.iterdir():
            dest = user_models_dir / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
                logger.info(f"Copied model directory: {item.name}")
            else:
                shutil.copy2(item, dest)

        logger.info(f"Successfully copied bundled models to {user_models_dir}")
    except Exception as e:
        logger.warning(f"Failed to copy bundled models: {e}")
        # Don't raise - we'll just download the models instead


class FunASRProvider(BaseSTTProvider):
    """
    FunASR 本地语音识别提供商
    
    特点:
    - 完全离线，隐私安全
    - 中文识别率比 Whisper 高 15-20%
    - 支持中文标点预测
    - 支持热词增强
    - 首次使用自动下载模型
    """

    name = "funasr"
    supports_streaming = True
    supports_timestamps = True

    def __init__(self, model_name: str | None = None):
        from app.infrastructure.config import SystemConfigService
        # Primary: Database config, Secondary: settings (env var)
        self.model_name = model_name or SystemConfigService.get_value("FUNASR_MODEL") or settings.FUNASR_MODEL
        self.device = SystemConfigService.get_value("FUNASR_DEVICE") or settings.FUNASR_DEVICE
        self._model = None
        self._funasr_available = self._check_dependencies()

    def _check_dependencies(self) -> bool:
        """检查依赖是否安装"""
        try:
            import funasr
            from funasr import AutoModel
            from modelscope import snapshot_download
            return True
        except ImportError as e:
            logger.warning(f"FunASR dependencies not installed: {e}")
            return False

    def is_available(self) -> bool:
        """检查 FunASR 是否可用"""
        return self._funasr_available

    def _load_model(self):
        """加载模型（延迟加载，首次使用时）"""
        if self._model is not None:
            return

        if not self._funasr_available:
            raise RuntimeError(
                "FunASR not installed. Please install: "
                "pip install funasr modelscope torch torchaudio"
            )

        # Try to copy bundled models before loading (for packaged apps)
        _copy_bundled_models_if_needed()

        try:
            from funasr import AutoModel

            model_config = FUNASR_MODELS.get(self.model_name, FUNASR_MODELS["paraformer-zh"])
            model_id = model_config["model_id"]

            logger.info(f"Loading FunASR model: {self.model_name} ({model_id}) on {self.device}")
            logger.info(f"Model cache directory: {settings.MODELS_DIR}")

            # Check if model needs to be downloaded
            if not FunASRManager.is_model_downloaded(self.model_name):
                logger.info(f"Model {self.model_name} not found locally, will download from ModelScope...")

            # 自动下载并加载模型 (使用 MODELSCOPE_CACHE 环境变量指定的路径)
            self._model = AutoModel(
                model=model_id,
                model_revision="v2.0.4",
                device=self.device,
            )

            logger.info(f"FunASR model loaded successfully: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load FunASR model: {e}")
            raise RuntimeError(f"Failed to load FunASR model: {e}")

    def list_models(self, language: VoiceLocale | None = None) -> list[str]:
        """
        获取可用模型列表
        
        Args:
            language: 按语言过滤
            
        Returns:
            list[str]: 模型名称列表
        """
        if language:
            # 根据语言过滤
            lang_map = {
                VoiceLocale.ZH_CN: ["paraformer-zh", "paraformer-zh-plus", "paraformer-zh-streaming", "paraformer-zh-en"],
                VoiceLocale.ZH_TW: ["paraformer-zh", "paraformer-zh-plus"],
                VoiceLocale.ZH_HK: ["paraformer-zh", "paraformer-zh-plus"],
                VoiceLocale.EN_US: ["paraformer-zh-en"],
                VoiceLocale.EN_GB: ["paraformer-zh-en"],
                VoiceLocale.AUTO: list(FUNASR_MODELS.keys()),
            }
            return lang_map.get(language, list(FUNASR_MODELS.keys()))

        return list(FUNASR_MODELS.keys())

    def get_default_model(self, language: VoiceLocale = VoiceLocale.ZH_CN) -> str:
        """获取默认模型"""
        defaults = {
            VoiceLocale.ZH_CN: "paraformer-zh",
            VoiceLocale.ZH_TW: "paraformer-zh",
            VoiceLocale.ZH_HK: "paraformer-zh",
            VoiceLocale.EN_US: "paraformer-zh-en",
            VoiceLocale.EN_GB: "paraformer-zh-en",
            VoiceLocale.AUTO: "paraformer-zh",
        }
        return defaults.get(language, "paraformer-zh")

    async def transcribe(self, options: STTOptions) -> STTResult:
        """
        识别语音
        
        Args:
            options: STT 选项
            
        Returns:
            STTResult: 识别结果
        """
        self._load_model()

        # 保存音频到临时文件
        import asyncio
        import tempfile

        suffix = f".{options.audio_format}" if options.audio_format else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(options.audio_data)
            tmp_path = tmp.name

        try:
            # FunASR 的 generate 是同步的，在线程池中运行
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,  # 使用默认线程池
                lambda: self._model.generate(input=tmp_path, batch_size=1)
            )

            # 解析结果
            if result and len(result) > 0:
                text = result[0].get("text", "").strip()

                # 检测语言
                detected_lang = self._detect_language(text)

                return STTResult(
                    text=text,
                    language=detected_lang,
                    duration_ms=None,  # FunASR 不直接返回时长
                    confidence=None,   # FunASR 不直接返回置信度
                )
            else:
                return STTResult(
                    text="",
                    language=options.language or VoiceLocale.ZH_CN,
                    duration_ms=0,
                    confidence=0,
                )

        finally:
            # 清理临时文件
            try:
                os.unlink(tmp_path)
            except:
                pass

    async def transcribe_stream(self, options: STTOptions) -> AsyncIterator[STTResult]:
        """
        流式识别（使用流式模型）
        
        注意：需要加载 paraformer-zh-streaming 模型
        """
        # 流式识别需要专门的流式模型
        # 这里简单实现为一次性返回
        result = await self.transcribe(options)
        yield result

    def _detect_language(self, text: str) -> VoiceLocale:
        """简单检测语言"""
        import re

        # 检查是否主要是中文
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text.replace(" ", ""))

        if total_chars == 0:
            return VoiceLocale.ZH_CN

        chinese_ratio = chinese_chars / total_chars

        if chinese_ratio > 0.5:
            return VoiceLocale.ZH_CN
        else:
            return VoiceLocale.EN_US


class FunASRManager:
    """
    FunASR 模型管理器
    
    用于预加载和管理多个模型实例
    """

    _instances: dict[str, FunASRProvider] = {}

    @classmethod
    def get_provider(cls, model_name: str = "paraformer-zh") -> FunASRProvider:
        """获取或创建 FunASR 提供商"""
        if model_name not in cls._instances:
            cls._instances[model_name] = FunASRProvider(model_name)
        return cls._instances[model_name]

    @classmethod
    def preload_model(cls, model_name: str = "paraformer-zh"):
        """预加载模型"""
        provider = cls.get_provider(model_name)
        try:
            provider._load_model()
            logger.info(f"FunASR model preloaded: {model_name}")
        except Exception as e:
            logger.error(f"Failed to preload model {model_name}: {e}")

    @classmethod
    def clear_cache(cls):
        """清除缓存"""
        cls._instances.clear()
        logger.info("FunASR cache cleared")

    @classmethod
    def get_model_path(cls, model_name: str = "paraformer-zh") -> Path | None:
        """
        获取模型存储路径
        
        Returns:
            Path: 模型在 MODELS_DIR 中的存储路径
        """
        model_config = FUNASR_MODELS.get(model_name, FUNASR_MODELS["paraformer-zh"])
        model_id = model_config["model_id"]
        # ModelScope stores models in: MODELS_DIR/hub/{model_id}
        return Path(settings.MODELS_DIR) / "hub" / model_id

    @classmethod
    def is_model_downloaded(cls, model_name: str = "paraformer-zh") -> bool:
        """
        检查模型是否已下载
        
        Returns:
            bool: True if model files exist in MODELS_DIR
        """
        model_path = cls.get_model_path(model_name)
        if model_path is None:
            return False
        # Check for common model files
        return (model_path / "model.pt").exists() or (model_path / "pytorch_model.bin").exists()
