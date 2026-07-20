import pytest
from unittest.mock import MagicMock, patch

from app.infrastructure.voice.stt.factory import STTFactory
from app.infrastructure.voice.stt.aliyun import AliyunProvider
from app.infrastructure.voice.stt.qwen3_asr import Qwen3ASRProvider
from app.infrastructure.voice.stt.whisper import WhisperProvider


def test_stt_factory_list_providers():
    """测试 STTFactory 列出所有可用的 Provider"""
    providers = STTFactory.list_available_providers()
    provider_names = [p["name"] for p in providers]
    assert "qwen3-asr" in provider_names
    assert "aliyun-sensevoice" in provider_names
    assert "whisper" in provider_names


@patch("app.infrastructure.config.service.SystemConfigService.get_value")
def test_stt_factory_resolve_qwen3(mock_get_value):
    """测试当数据库配置为 qwen3-asr 时，Factory 返回 Qwen3ASRProvider"""
    mock_get_value.side_effect = lambda key, default=None: "qwen3-asr" if key == "STT_PROVIDER" else None
    
    provider = STTFactory.get_provider()
    # 视乎本地 Qwen3-ASR 是否可用，可能返回 Qwen3ASRProvider 或回退
    if provider.is_available():
        assert provider.name == "qwen3-asr"
    else:
        assert provider.name in ["openai-whisper", "aliyun-sensevoice"]


@patch("app.infrastructure.config.service.SystemConfigService.get_value")
def test_stt_factory_resolve_aliyun(mock_get_value):
    """测试当数据库配置为 aliyun-sensevoice 时，Factory 返回 AliyunProvider"""
    mock_get_value.side_effect = lambda key, default=None: "aliyun-sensevoice" if key == "STT_PROVIDER" else "test-api-key"
    
    # 模拟 API Key 已配置以使得 is_available 返回 True
    with patch.object(AliyunProvider, "is_available", return_value=True):
        provider = STTFactory.get_provider()
        assert provider.name == "aliyun-sensevoice"
        assert isinstance(provider, AliyunProvider)


def test_aliyun_provider_metadata():
    """测试 AliyunProvider 元数据与模型列表"""
    provider = AliyunProvider()
    assert provider.name == "aliyun-sensevoice"
    assert provider.supports_streaming is False
    assert provider.supports_timestamps is False
    
    models = provider.list_models()
    assert "qwen-audio-turbo" in models
    assert "paraformer-v1" in models


@patch("app.infrastructure.config.service.SystemConfigService.get_value")
def test_aliyun_provider_api_key(mock_get_value):
    """测试 AliyunProvider 优先从系统配置数据库读取 API Key"""
    mock_get_value.return_value = "db-secret-key"
    
    provider = AliyunProvider()
    assert provider.is_available() is True
    
    client = provider._get_client()
    assert client.api_key == "db-secret-key"
    assert str(client.base_url) == "https://dashscope.aliyuncs.com/compatible-mode/v1/"
