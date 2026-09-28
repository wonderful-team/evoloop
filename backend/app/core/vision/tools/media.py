"""Media facade tool — single unified entry for image & video analyze/generation.

把 ``image``/``video`` 两个孪生 facade（同构 action=prompt/source/question/model）
收敛为单一 ``media`` 工具（2026-09 工具面收敛）：

- analyze:  分析一张图片或一段视频（kind 可由 source 扩展名自动推断）。
- generate: 文生/图生 图片或视频（kind 必填，无 source 可推断）。

业务实现仍住 image.py / video.py（_analyze/_generate），本模块只做
kind 判别与参数归一，与 plan/tasks/macro facade 同范式。
"""

import logging
from typing import Annotated, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.core.vision.tools.image import _analyze as _analyze_image
from app.core.vision.tools.image import _generate as _generate_image
from app.core.vision.tools.video import _analyze as _analyze_video
from app.core.vision.tools.video import _generate as _generate_video

logger = logging.getLogger(__name__)

#: kind 自动推断的扩展名表（URL 先剥离 query string 再取后缀）
_IMAGE_EXTS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".heif", ".tiff", ".ico"}
)
_VIDEO_EXTS = frozenset(
    {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv"}
)

_IMAGE_DEFAULT_SIZE = "1024x1024"
_VIDEO_DEFAULT_SIZE = "1920x1080"


def infer_media_kind(source: str) -> Literal["image", "video"] | None:
    """从 source（本地路径或 URL）的扩展名推断媒体类型，推不出返回 None。"""
    path = source.split("?", 1)[0].split("#", 1)[0].rsplit(".", 1)
    if len(path) != 2:
        return None
    ext = f".{path[1].lower()}"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    return None


@evoloop_tool(
    name="media",
    is_state_mutating=True,
    affected_path_keys=["source"],
    summary_template="evoloop.tool_summary.media",
)
async def media(
    action: Literal["analyze", "generate"] = "analyze",
    kind: Literal["image", "video"] | None = None,
    prompt: str | None = None,
    source: str | None = None,
    seconds: int = 5,
    size: str | None = None,
    question: str = "Describe this media in detail.",
    include_ax_tree: bool = False,
    model: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """统一媒体入口——分析或生成图片/视频。

    Actions:
    - analyze:  分析图片（VisionEngine 直接分析，可选注入 UI 树接地）或视频
                （先抽关键帧逐帧分析）。source 为本地路径或公开 URL。
    - generate: 文生/图生 图片或视频，经网关 OpenAI 标准接口调用生成模型，
                结果上传云端并返回公网链接。

    WHEN TO USE:
    - 用户发来图片/视频问"这是什么/发生了什么" → analyze（kind 可省略，自动识别）。
    - 用户说"画一只猫/生成一张海报/来一段海浪视频" → generate（kind 必填）。

    Args:
        action: 执行的动作（analyze / generate）。
        kind: 媒体类型（image / video）。analyze 时可省略——由 source 扩展名
              自动推断；generate 时**必填**（无 source 可推断）。
        prompt: generate 时的文本提示词。
        source: analyze 时的媒体来源（本地绝对路径、uploads/ 相对路径、
                /api/v1/files/raw 链接或公网 URL）；generate 时可选参考图
                （图生图/图生视频）。
        seconds: generate 视频时长（秒），仅 kind=video 时生效。
        size: generate 输出尺寸；省略时 image=1024x1024，video=1920x1080。
        question: analyze 时对媒体内容的问题或指令。
        include_ax_tree: analyze 图片时是否注入当前平台 UI 树（仅 kind=image 生效）。
        model: 可选指定生成模型；缺省由网关默认模型路由。
    """
    if action == "analyze":
        if not source:
            return "Error: action=analyze requires `source` (local path or URL)."
        resolved_kind = kind or infer_media_kind(source)
        if resolved_kind == "video":
            return await _analyze_video(source, question)
        if resolved_kind == "image":
            return await _analyze_image(source, question, include_ax_tree)
        return (
            f"Error: cannot infer media kind from source '{source}'. "
            "Please pass kind='image' or kind='video' explicitly."
        )

    if not kind:
        return (
            "Error: action=generate requires `kind` ('image' or 'video') — "
            "there is no source to infer it from."
        )
    resolved_size = size or (
        _VIDEO_DEFAULT_SIZE if kind == "video" else _IMAGE_DEFAULT_SIZE
    )
    if kind == "video":
        return await _generate_video(prompt, source, seconds, resolved_size, model, config)
    return await _generate_image(prompt, source, resolved_size, model, config)
