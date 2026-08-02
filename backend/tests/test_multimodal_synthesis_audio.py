from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.learning.multimodal_synthesizer import (
    MultimodalSkillSynthesizer,
    RecordingSession,
)
from app.infrastructure.voice.stt.base import STTResult, VoiceLocale


@pytest.mark.asyncio
@patch("app.core.learning.multimodal_synthesizer.VisionLLMFactory.create_vision_llm_async", new_callable=AsyncMock)
@patch("app.core.learning.multimodal_synthesizer.SystemConfigService.get_value")
@patch("app.core.learning.multimodal_synthesizer.subprocess.run")
@patch("app.core.learning.multimodal_synthesizer.os.path.exists")
@patch("app.core.learning.multimodal_synthesizer.os.path.getsize")
@patch("app.infrastructure.voice.transcribe_file")
@patch("app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer._get_video_info")
@patch("app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer._fetch_events")
@patch("app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer._extract_and_compress_frames")
@patch("app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer._call_vision_llm")
@patch("app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer._parse_llm_response")
@patch("app.core.learning.multimodal_synthesizer.MultimodalSkillSynthesizer._compile_macro_from_events")
async def test_multimodal_synthesis_audio_flow(
    mock_compile_macro,
    mock_parse_llm,
    mock_call_vision,
    mock_extract_frames,
    mock_fetch_events,
    mock_get_video_info,
    mock_transcribe,
    mock_getsize,
    mock_exists,
    mock_sub_run,
    mock_get_config_value,
    mock_create_vision,
):
    """测试多模态合成流中正确调用了音频提取和语音识别"""
    # 模拟 Vision LLM 创建
    mock_create_vision.return_value = MagicMock()
    mock_get_config_value.return_value = "mock-vision-model"

    # 模拟外部文件系统和进程
    mock_exists.return_value = True
    mock_getsize.return_value = 5000  # 文件大小足够

    # 模拟 subprocess.run 返回成功
    mock_sub_run.return_value = MagicMock(returncode=0)

    # 模拟视频和事件数据
    mock_get_video_info.return_value = MagicMock(width=1080, height=1920, duration=10.0)
    mock_fetch_events.return_value = [
        MagicMock(action_type="touch_down", mouse_x=500, mouse_y=500, timestamp=1.0, source="user")
    ]
    mock_extract_frames.return_value = []

    # 模拟语音识别结果
    mock_transcribe.return_value = STTResult(
        text="我们现在开始打开抖音然后点击搜索",
        language=VoiceLocale.ZH_CN,
        duration_ms=5000
    )

    # 模拟 LLM 和宏处理
    mock_call_vision.return_value = "llm_output_data"
    mock_parse_llm.return_value = MagicMock(macro_script="compiled_macro")
    mock_compile_macro.return_value = "compiled_macro"

    # 初始化会话数据
    recording = RecordingSession(
        video_path="/path/to/mock_video.mp4",
        session_id="mock_session_id",
        task_description="打开网页搜索"
    )

    synthesizer = MultimodalSkillSynthesizer()

    # 执行合成
    with patch("app.core.learning.multimodal_synthesizer.os.unlink") as mock_unlink:
        await synthesizer.synthesize(recording)

        # 验证临时音频文件的清理
        mock_unlink.assert_called_once()

    # 确认 FFmpeg 提取音频的命令正确执行了
    ffmpeg_called = False
    for call in mock_sub_run.call_args_list:
        args = call[0][0]
        if isinstance(args, list) and len(args) > 0 and "ffmpeg" in args[0]:
            ffmpeg_called = True
            assert "-vn" in args
            assert "pcm_s16le" in args
            break
    assert ffmpeg_called, "FFmpeg audio extraction was not called"

    # 确认 ASR 被成功调用
    mock_transcribe.assert_called_once()

    # 确认 ASR 转写出来的文本被当做参数传给了 Vision LLM 调用
    mock_call_vision.assert_called_once()
    call_args = mock_call_vision.call_args[1]
    assert call_args["voice_transcript"] == "我们现在开始打开抖音然后点击搜索"
