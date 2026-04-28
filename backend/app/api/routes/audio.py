"""
Audio processing API - Speech-to-Text and Text-to-Speech

使用标准化 Voice 模块：
- TTS: Edge-TTS (免费，无需 API Key)
- STT: FunASR (本地，中文优化) / Whisper (云端，备选)
"""

import logging
import os
import tempfile
from typing import Optional, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from fastapi.responses import StreamingResponse, FileResponse

from app.api.deps import require_benefit
from app.api.responses import BaseAPIResponse
from app.core.voice import (
    get_tts_provider,
    get_stt_provider,
    TTSOptions,
    STTOptions,
    VoiceLocale,
)
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.api.schemas.audio import TranscriptionResponse, TTSRequest, TTSResponse, VoiceListResponse, STTProvidersResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["audio"])


# ============ TTS Endpoints ============

@router.get("/voices", response_model=VoiceListResponse)
async def list_voices():
    """
    获取可用 TTS 声音列表
    
    返回 Edge-TTS 支持的所有声音（中文、英文、日文、韩文等）
    """
    from app.core.voice import list_tts_voices
    
    try:
        voices = list_tts_voices()
        return VoiceListResponse(voices=voices)
    except Exception as e:
        logger.error(f"Failed to list voices: {e}")
        raise HTTPException(500, f"Failed to list voices: {str(e)}")


@router.post("/tts", response_model=TTSResponse, dependencies=[Depends(require_benefit("voice"))])
async def text_to_speech(request: TTSRequest):
    """
    文字转语音（返回音频文件 URL）
    
    使用 Edge-TTS，完全免费，无需 API Key。
    
    Args:
        text: 要合成的文本（最多 4096 字符）
        voice_id: 声音 ID，默认 "zh-CN-XiaoxiaoNeural"（晓晓）
        speed: 语速，0.5-2.0，默认 1.0
        format: 音频格式，只支持 mp3
    
    Returns:
        TTSResponse: 包含音频文件 URL
    """
    if len(request.text) > 4096:
        raise HTTPException(400, "Text too long. Max 4096 characters.")
    
    try:
        # 获取 TTS 提供商
        provider = get_tts_provider()
        
        # 构建选项
        locale = VoiceLocale.ZH_CN
        if request.voice_id.startswith("en-"):
            locale = VoiceLocale.EN_US
        elif request.voice_id.startswith("ja-"):
            locale = VoiceLocale.JA_JP
        elif request.voice_id.startswith("ko-"):
            locale = VoiceLocale.KO_KR
        
        options = TTSOptions(
            text=request.text,
            voice_id=request.voice_id,
            speed=request.speed,
            format="mp3",  # Edge-TTS 只支持 mp3
            locale=locale
        )
        
        # 合成语音
        result = await provider.synthesize(options)
        
        # 保存到临时文件
        tts_dir = os.path.join(tempfile.gettempdir(), "evoloop_tts")
        os.makedirs(tts_dir, exist_ok=True)
        
        import uuid
        filename = f"tts_{uuid.uuid4().hex}.mp3"
        file_path = os.path.join(tts_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(result.audio_data)
        
        logger.info(f"TTS synthesized: {file_path}, voice={request.voice_id}")
        
        return TTSResponse(url=f"/api/v1/audio/tts-file/{filename}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        raise HTTPException(500, f"TTS failed: {str(e)}")


@router.post("/tts-stream")
async def text_to_speech_stream(
    text: str = Form(...),
    voice_id: str = Form("zh-CN-XiaoxiaoNeural"),
    speed: float = Form(1.0),
    format: str = Form("mp3")
):
    """
    文字转语音（流式返回）
    
    直接返回音频流，适合实时播放。
    注意：Edge-TTS 不支持真正的流式合成，服务器会先完整合成，然后分块传输。
    
    Args:
        text: 要合成的文本（FormData）
        voice_id: 声音 ID（FormData）
        speed: 语速（FormData）
        format: 音频格式（FormData）
    
    Returns:
        StreamingResponse: 音频流（audio/mpeg）
    """
    if len(text) > 4096:
        raise HTTPException(400, "Text too long. Max 4096 characters.")
    
    try:
        provider = get_tts_provider()
        
        # 检查文本内容（清理后）
        from app.core.voice.utils import optimize_for_tts
        cleaned_text = optimize_for_tts(text)
        if not cleaned_text or not cleaned_text.strip():
            raise HTTPException(400, "Text is empty after processing. Please provide valid text content.")
        
        # 确定语言
        locale = VoiceLocale.ZH_CN
        if voice_id.startswith("en-"):
            locale = VoiceLocale.EN_US
        elif voice_id.startswith("ja-"):
            locale = VoiceLocale.JA_JP
        elif voice_id.startswith("ko-"):
            locale = VoiceLocale.KO_KR
        
        options = TTSOptions(
            text=text,
            voice_id=voice_id,
            speed=speed,
            format="mp3",
            locale=locale
        )
        
        # 使用流式接口
        async def generate():
            async for chunk in provider.synthesize_stream(options):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=3600",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS stream failed: {e}")
        raise HTTPException(500, f"TTS failed: {str(e)}")


@router.get("/tts-file/{filename}")
async def get_tts_file(filename: str):
    """
    获取生成的音频文件
    
    Args:
        filename: 文件名
        
    Returns:
        FileResponse: 音频文件
    """
    tts_dir = os.path.join(tempfile.gettempdir(), "evoloop_tts")
    file_path = os.path.join(tts_dir, filename)
    
    # 安全检查
    if not os.path.abspath(file_path).startswith(os.path.abspath(tts_dir)):
        raise HTTPException(403, "Invalid filename")
    
    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")
    
    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "public, max-age=3600",
        }
    )


# ============ STT Endpoints ============

@router.get("/stt/providers", response_model=STTProvidersResponse)
async def list_stt_providers():
    """
    获取可用 STT 提供商列表
    
    返回所有可用的语音识别提供商及其状态
    """
    from app.core.voice import list_stt_providers
    
    try:
        providers = list_stt_providers()
        return STTProvidersResponse(providers=providers)
    except Exception as e:
        logger.error(f"Failed to list STT providers: {e}")
        raise HTTPException(500, f"Failed to list providers: {str(e)}")


@router.post("/transcribe", response_model=TranscriptionResponse, dependencies=[Depends(require_benefit("voice"))])
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    model: str = Form("auto"),
    prompt: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
):
    """
    语音转文字
    
    优先使用 FunASR（本地，中文优化），不可用则回退到 Whisper（云端）。
    
    Args:
        file: 音频文件（webm, mp3, wav, m4a 等）
        language: 语言代码（zh, en, ja 等）或 auto 自动检测
        model: 模型名称，默认 auto（自动选择）
        prompt: 可选提示词，提高特定术语识别率
        provider: 指定提供商（funasr/whisper/auto）
    
    Returns:
        TranscriptionResponse: 识别结果
    """
    # 验证文件
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(400, "Invalid file type. Expected audio file.")
    
    # 读取文件内容
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file")
    
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large. Max 50MB.")
    
    try:
        # 确定语言
        locale = VoiceLocale.AUTO
        if language and language != "auto":
            lang_map = {
                "zh": VoiceLocale.ZH_CN,
                "zh-CN": VoiceLocale.ZH_CN,
                "zh-TW": VoiceLocale.ZH_TW,
                "zh-HK": VoiceLocale.ZH_HK,
                "en": VoiceLocale.EN_US,
                "en-US": VoiceLocale.EN_US,
                "en-GB": VoiceLocale.EN_GB,
                "ja": VoiceLocale.JA_JP,
                "ko": VoiceLocale.KO_KR,
            }
            locale = lang_map.get(language, VoiceLocale.AUTO)
        
        # 选择提供商
        prefer_local = provider != "whisper"  # 只要不是指定 whisper，都优先本地
        stt_provider = get_stt_provider(prefer_local=prefer_local)
        
        logger.info(f"Using STT provider: {stt_provider.name} for {len(content)} bytes audio")
        
        # 构建选项
        options = STTOptions(
            audio_data=content,
            audio_format=_get_audio_format(file.filename, file.content_type),
            language=locale,
            model=model if model != "auto" else None,
            prompt=prompt,
        )
        
        # 执行识别
        result = await stt_provider.transcribe(options)
        
        # 估算音频时长（简化计算，假设 16kHz 16bit mono）
        estimated_duration = len(content) / 32000  # 粗略估算
        
        return TranscriptionResponse(
            text=result.text,
            duration=estimated_duration,
            language=result.language.value,
            confidence=result.confidence,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(500, f"Transcription failed: {str(e)}")


def _get_audio_format(filename: Optional[str], content_type: str) -> str:
    """从文件名或 content-type 推断音频格式"""
    # 从 content_type
    type_map = {
        "audio/webm": "webm",
        "audio/mp3": "mp3",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
    }
    
    fmt = type_map.get(content_type)
    if fmt:
        return fmt
    
    # 从文件名
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        ext_map = {
            ".webm": "webm",
            ".mp3": "mp3",
            ".wav": "wav",
            ".m4a": "m4a",
            ".mp4": "m4a",
            ".ogg": "ogg",
            ".opus": "opus",
        }
        fmt = ext_map.get(ext)
        if fmt:
            return fmt
    
    return "webm"  # 默认


@router.post("/transcribe-stream")
async def transcribe_stream(
    file: UploadFile = File(...),
    language: str = Form("auto")
):
    """
    流式语音识别（暂未实现）
    
    预留接口，未来支持 WebSocket 实时识别。
    """
    raise HTTPException(501, "Streaming transcription not implemented yet. Use /transcribe instead.")
