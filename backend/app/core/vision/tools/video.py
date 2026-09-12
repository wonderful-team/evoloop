"""Video facade tool — single unified entry for video analyze & generation.

把「视频分析」与「生视频」收敛为单一 ``video`` 工具，按 ``action`` 分发，与
``image``/``vault``/``schedule`` facade 对齐：
- analyze:  提取视频关键帧交给 VisionEngine 分析内容（原视频引用分析能力）。
- generate: 文生视频 / 图生视频，走 OpenAI 标准 ``videos.create_and_poll``
            接口（经网关统一代理，模型由网关目录动态提供）。
"""
import logging
from typing import Annotated, Literal, TypeAlias, cast

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.core.vision.tools._media import (
    load_source_bytes,
    remove_file,
    stash_media_ref,
    write_temp,
)

logger = logging.getLogger(__name__)

# OpenAI 标准 videos.create 的 size 参数（对齐 openai SDK VideoSize）
VideoSize: TypeAlias = Literal["720x1280", "1280x720", "1024x1792", "1792x1024"]


@evoloop_tool(
    name="video",
    is_state_mutating=True,
    affected_path_keys=["source"],
    summary_template="evoloop.tool_summary.video",
)
async def video(
    action: Literal["analyze", "generate"] = "analyze",
    prompt: str | None = None,
    source: str | None = None,
    seconds: int = 5,
    size: str = "1920x1080",
    question: str = "Describe this video in detail.",
    model: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一视频入口——分析一段视频或生成一段视频。

    Actions:
    - analyze:  提取视频关键帧（VideoService.extract_keyframes）并交给 VisionEngine
                分析内容。source 为本地视频路径或公开 URL。
    - generate: 文生视频（prompt）或图生视频（prompt + source 参考图），
                经网关 OpenAI 标准接口（videos.create_and_poll）生成，结果上传云端并返回公网链接。

    WHEN TO USE:
    - 用户发来视频问"这里面发生了什么 / 总结一下" → analyze。
    - 用户说"生成一段海浪视频 / 基于这张图做一段视频" → generate。

    Args:
        action: 执行的动作（analyze / generate）。
        prompt: generate 时的文本提示词（文生视频/图生视频描述）。
        source: analyze 时的本地视频路径或公开 URL；generate 时可选参考图路径/URL（图生视频）。
        seconds: generate 视频时长（秒）。
        size: generate 视频分辨率（OpenAI 标准，如 1920x1080 / 720x720）。
        question: analyze 时对视频内容的问题。
        model: 可选指定视频模型；缺省由网关默认视频模型路由。
    """
    if action == "generate":
        return await _generate(prompt, source, seconds, size, model, config)

    return await _analyze(source, question)


async def _analyze(source: str | None, question: str) -> str:
    """Analyze a video by extracting keyframes and running vision analysis."""
    if not source:
        return "Error: action=analyze requires `source` (local video path or URL)."

    try:
        from app.core.vision import vision_engine
        from app.infrastructure.vision import VisionTask
        from app.infrastructure.vision.video.service import VideoService

        frames = await VideoService.extract_keyframes(source, count=4)
        if not frames:
            return "Error: could not extract any frames from the video."

        # 逐帧送入 VisionEngine 分析（frame.data 为 JPEG 字节）
        summary_lines = []
        for i, frame in enumerate(frames, start=1):
            prompt = f"[Frame {i}/{len(frames)}] {question}"
            frame_path = await write_temp(frame.data, ".jpg")
            try:
                result = await vision_engine.process(
                    task=VisionTask.ANALYZE,
                    image_source=frame_path,
                    prompt=prompt,
                )
                if result.success:
                    summary_lines.append(f"Frame {i}: {result.summary}")
            except Exception as e:
                logger.warning(f"[Video] Frame {i} analysis failed: {e}", exc_info=True)

        if not summary_lines:
            return "Error: vision analysis produced no summary."
        return "\n".join(summary_lines)
    except Exception as e:
        logger.exception(f"[Video] analyze failed: {e}")
        return f"Error: video analysis failed: {str(e)}"


async def _generate(
    prompt: str | None,
    source: str | None,
    seconds: int,
    size: str,
    model: str | None,
    config,
) -> str:
    """Generate a video via OpenAI-standard videos API (through the gateway)."""
    if not prompt:
        return "Error: action=generate requires `prompt` (text description)."

    try:
        from openai.types.video_seconds import VideoSeconds

        from app.core.evocloud import evocloud_manager
        from app.infrastructure.vision.generation import create_generation_client

        try:
            client = create_generation_client()
        except ValueError as e:
            return f"Error: {e}"

        # model 未指定时，从网关视频模型目录自动选第一个可用模型
        if not model:
            from app.infrastructure.llm.platform_service import llm_platform_service

            video_models = llm_platform_service.get_video_models()
            if not video_models:
                await llm_platform_service.fetch_platform_models(force_refresh=True)
                video_models = llm_platform_service.get_video_models()
            if video_models:
                model = video_models[0].model_id
                logger.info("[Video] auto-selected video model: %s", model)

        # 图生视频：参考图统一转为公网 URL（Ark 从 URL 拉取；本地路径先上传 MC）
        input_reference: str | None = None
        if source:
            if source.startswith(("http://", "https://")):
                input_reference = source
            else:
                source_bytes = await load_source_bytes(source, config)
                tmp = await write_temp(source_bytes, ".png")
                try:
                    input_reference = await evocloud_manager.api.upload_chat_media(tmp, "image")
                finally:
                    await remove_file(tmp)

        # 轮询上限：防止上游任务卡死导致会话无限挂起（openai SDK create_and_poll 无界）
        import asyncio

        poll_timeout = 900.0  # 15 分钟
        try:
            if input_reference:
                video_obj = await asyncio.wait_for(
                    client.videos.create_and_poll(
                        model=model or "",  # 空 model 由网关默认视频模型路由
                        prompt=prompt,
                        seconds=cast(VideoSeconds, seconds),
                        size=cast(VideoSize, size),
                        input_reference=input_reference,
                    ),
                    timeout=poll_timeout,
                )
            else:
                video_obj = await asyncio.wait_for(
                    client.videos.create_and_poll(
                        model=model or "",
                        prompt=prompt,
                        seconds=cast(VideoSeconds, seconds),
                        size=cast(VideoSize, size),
                    ),
                    timeout=poll_timeout,
                )
        except TimeoutError:
            return (
                f"Error: video generation timed out after {int(poll_timeout)}s. "
                f"The task may still complete upstream; please retry later."
            )

        if video_obj.status != "completed":
            return (
                f"Error: video generation did not complete (status={video_obj.status}, "
                f"error={video_obj.error})"
            )

        # 下载到临时文件 → 上传 Member Center 换公网 URL（云端为权威存储）
        data = await _download_video_bytes(client, video_obj.id)
        tmp_path = await write_temp(data, ".mp4")
        try:
            public_url = await evocloud_manager.api.upload_chat_media(tmp_path, "video")
        finally:
            await remove_file(tmp_path)

        # 结构化引用直传：AI 消息持久化时合并（不依赖模型复述链接）
        stash_media_ref("video", public_url, "generated video")

        return (
            f"[Video: generated video]({public_url})\n\n"
            f"(视频已生成并上传。你的最终回复中无需重复该链接——界面会自动展示视频播放器；"
            f"如需在正文中提及，请原样保留上面的视频链接。)"
        )
    except Exception as e:
        logger.exception(f"[Video] generate failed: {e}")
        return f"Error: video generation failed: {str(e)}"


async def _download_video_bytes(client, video_id: str) -> bytes:
    """Download a completed video's content and return its bytes."""
    response = await client.with_raw_response.videos.download_content(video_id)
    return await response.aread()
