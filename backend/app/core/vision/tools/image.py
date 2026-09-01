"""Image facade tool — single unified entry for image analyze & generation.

把「图片分析」与「生图」收敛为单一 ``image`` 工具，按 ``action`` 分发，与
``vault``/``schedule``/``task`` facade 对齐：
- analyze:  用 VisionEngine 分析一张图片（原 ``analyze_image`` 能力）。
- generate: 文生图 / 图生图，走 OpenAI 标准 ``images.generate`` / ``images.edit``
            接口（经网关统一代理，模型由网关目录动态提供）。
"""

import logging
from typing import Annotated, Literal, TypeAlias, cast

from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.core.vision import vision_engine
from app.infrastructure.vision import VisionTask
from app.infrastructure.vision.types import PlatformType
from app.utils.template import render_template

logger = logging.getLogger(__name__)

# OpenAI 标准 images.generate/edit 的 size 参数（对齐 openai SDK 内联 Literal）
ImageSize: TypeAlias = Literal[
    "256x256", "512x512", "1024x1024", "1536x1024", "1024x1536", "1792x1024", "1024x1792", "auto"
]
ImageEditSize: TypeAlias = Literal[
    "256x256", "512x512", "1024x1024", "1536x1024", "1024x1536", "auto"
]


@evoloop_tool(
    name="image",
    is_state_mutating=True,
    affected_path_keys=["source", "output_path"],
    summary_template="evoloop.tool_summary.image",
)
async def image(
    action: Literal["analyze", "generate"] = "analyze",
    prompt: str | None = None,
    source: str | None = None,
    output_path: str = "uploads/generated_image.png",
    size: str = "1024x1024",
    question: str = "Describe this image in detail.",
    include_ax_tree: bool = False,
    model: str | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """统一图像入口——分析一张图片或生成一张图片。

    Actions:
    - analyze:  分析本地图片文件路径或公开 URL。可用 question 指定问题，
                可选 include_ax_tree 注入 macOS/Android UI 树用于接地。
    - generate: 文生图（prompt）或图生图（prompt + source 参考图），
                经网关 OpenAI 标准接口调用图像模型，结果存到 output_path 并返回 markdown 链接。

    WHEN TO USE:
    - 用户发来图片问"这是什么 / 描述一下 / 看看布局问题" → analyze。
    - 用户说"画一只猫 / 生成一张海报 / 基于这张图做个变体" → generate。

    Args:
        action: 执行的动作（analyze / generate）。
        prompt: generate 时的文本提示词（文生图/图生图描述）。
        source: analyze 时的本地图片绝对路径或公开 URL；generate 时可选参考图路径/URL（图生图）。
        output_path: generate 输出保存路径（建议 uploads/... 便于聊天内引用）。
        size: generate 输出尺寸（OpenAI 标准枚举，如 1024x1024 / 1024x1536 / 1536x1024）。
        question: analyze 时对图片的问题或指令。
        include_ax_tree: analyze 时是否注入当前平台 UI Accessibility 树。
        model: 可选指定图像模型；缺省由网关默认图像模型路由。
    """
    if action == "generate":
        return await _generate(prompt, source, output_path, size, model, config)

    return await _analyze(source, question, include_ax_tree)


async def _analyze(source: str | None, question: str, include_ax_tree: bool) -> str:
    """Analyze an image (originally analyze_image)."""
    if not source:
        return "Error: action=analyze requires `source` (local image path or URL)."

    final_prompt = question

    if include_ax_tree:
        try:
            ctx = ContextManager.current()
            current_ecosystem = ctx.metadata.get("current_ecosystem")

            if current_ecosystem == PlatformType.ANDROID.value:
                from app.infrastructure.drivers.adb import adb_driver

                ax_tree = adb_driver.dump_ui()
                tree_label = "Android UI Hierarchy"
            else:
                from app.infrastructure.drivers.macos import macos_driver

                ax_tree = macos_driver.dump_ax_tree()
                tree_label = "macOS Accessibility (AX) Tree"

            if ax_tree and "Error" not in ax_tree:
                final_prompt = render_template(
                    "core/vision/vision_context.prompt.j2",
                    tree_label=tree_label,
                    ax_tree=ax_tree,
                )
                logger.info(f"[Image] Injected {tree_label} into prompt via template.")
        except Exception as e:
            logger.warning(f"[Image] Failed to inject AX Tree: {e}", exc_info=True)

    result = await vision_engine.process(
        task=VisionTask.ANALYZE, image_source=source, prompt=final_prompt
    )

    if result.success:
        return result.summary or "Image analysis completed."
    return f"Error: {result.metadata.get('error', 'Unknown error')}"


async def _generate(
    prompt: str | None,
    source: str | None,
    output_path: str,
    size: str,
    model: str | None,
    config,
) -> str:
    """Generate an image via OpenAI-standard images API (through the gateway)."""
    if not prompt:
        return "Error: action=generate requires `prompt` (text description)."

    try:
        from openai._types import FileTypes

        from app.infrastructure.vision.generation import create_generation_client

        try:
            client = create_generation_client()
        except ValueError as e:
            return f"Error: {e}"

        # model 未指定时，从网关图像模型目录自动选第一个可用模型
        if not model:
            from app.infrastructure.llm.platform_service import llm_platform_service

            image_models = llm_platform_service.get_image_models()
            if not image_models:
                await llm_platform_service.fetch_platform_models(force_refresh=True)
                image_models = llm_platform_service.get_image_models()
            if image_models:
                model = image_models[0].model_id
                logger.info("[Image] auto-selected image model: %s", model)

        if source:
            # 图生图：OpenAI 标准 images.edit（source 为本地路径/URL）
            resp = await client.images.edit(
                model=model or "",
                prompt=prompt,
                image=cast(FileTypes, source),
                n=1,
                size=cast(ImageEditSize, size),
                response_format="url",
            )
        else:
            resp = await client.images.generate(
                model=model or "",  # 空 model 由网关默认图像模型路由
                prompt=prompt,
                n=1,
                size=cast(ImageSize, size),
                response_format="url",
            )

        if not resp.data:
            return "Error: image generation returned no result."

        image_url = resp.data[0].url
        if not image_url:
            return "Error: image generation returned no URL."

        # 保存到本地 uploads 命名空间，便于聊天内引用与持久化
        from app.core.file.tools.utils import resolve_and_validate_path

        resolved = await resolve_and_validate_path(output_path, config)
        await _download_to_path(image_url, resolved)
        return f"[Image: generated image]({output_path})"
    except Exception as e:
        logger.exception(f"[Image] generate failed: {e}")
        return f"Error: image generation failed: {str(e)}"


async def _download_to_path(url: str, path: str) -> None:
    """Download a URL to a local path (async, no sync blocking)."""
    import os

    import aiofiles
    import httpx

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        async with aiofiles.open(path, "wb") as f:
            await f.write(resp.content)
