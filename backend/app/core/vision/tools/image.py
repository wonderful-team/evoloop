"""Image business ops — analyze & generate implementation (no tool registration).

2026-09 工具面收敛：``image`` 工具并入 ``media`` facade（media.py 按 kind 分发），
本模块保留纯业务函数 ``_analyze`` / ``_generate``，供 facade 与测试直接调用。
"""

import logging
from typing import Literal, TypeAlias, cast

from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.vision import vision_engine
from app.core.vision.tools._media import (
    download_bytes,
    load_source_bytes,
    remove_file,
    stash_media_ref,
    write_temp,
)
from app.infrastructure.vision import VisionTask
from app.infrastructure.vision.types import PlatformType
from app.utils.template import render_template

logger = logging.getLogger(__name__)

# OpenAI 标准 images.generate/edit 的 size 参数（对齐 openai SDK 内联 Literal）
ImageSize: TypeAlias = Literal[
    "256x256", "512x512", "1024x1024", "1536x1024", "1024x1536", "1792x1024", "1024x1792", "auto"
]


async def _analyze(
    source: str | None,
    question: str = "Describe this image in detail.",
    include_ax_tree: bool = False,
) -> str:
    """Analyze an image (originally analyze_image)."""
    if not source:
        return "Error: action=analyze requires `source` (local image path or URL)."

    # 非公网 URL 一律先解析为本地绝对路径（支持 uploads/ 相对路径与 /api/ raw 链接）
    if not source.startswith(("http://", "https://")):
        from app.core.vision.tools._media import resolve_media_source

        try:
            source = await resolve_media_source(source, config=None)
        except (ValueError, FileNotFoundError, OSError) as e:
            return f"Error: cannot resolve image source '{source}': {e}"
        import os

        if not os.path.isfile(source):
            return f"Error: image not found: {source}"

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
    error = str(result.metadata.get("error", "Unknown error"))
    if "no vision model" in error:
        return (
            "Error: no vision model is configured for this account, "
            "so image content cannot be analyzed directly. "
            "For image-to-image workflows, call this tool with action=generate "
            "and pass the reference via `source` — the image generation model "
            "will read the reference image itself (style, composition, subject)."
        )
    return f"Error: {error}"


async def _generate(
    prompt: str | None,
    source: str | None = None,
    size: str = "1024x1024",
    model: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    """Generate an image via OpenAI-standard images API (through the gateway)."""
    if not prompt:
        return "Error: action=generate requires `prompt` (text description)."

    try:
        from app.core.evocloud import evocloud_manager
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
                # 网关目录可能含未实际接通的条目（如 5.0-lite 曾被 Ark 拒
                # UnsupportedModel）；已验证可用的优先，目录序兜底
                preferred = [m for m in image_models if "pro" in (m.model_id or "").lower()]
                pick = (preferred or image_models)[0]
                model = pick.model_id
                logger.info("[Image] auto-selected image model: %s", model)

        # 图生图：参考图统一转为公网 URL（Ark 直接拉取；本地路径先上传 MC）
        extra_body: dict = {}
        if source:
            if source.startswith(("http://", "https://")):
                source_url = source
            else:
                source_bytes = await load_source_bytes(source, config)
                tmp = await write_temp(source_bytes, ".png")
                try:
                    source_url = await evocloud_manager.api.upload_chat_media(tmp, "image")
                finally:
                    await remove_file(tmp)
            extra_body = {"image": [source_url]}

        resp = await client.images.generate(
            model=model or "",  # 空 model 由网关默认图像模型路由
            prompt=prompt,
            n=1,
            size=cast(ImageSize, size),
            response_format="url",
            extra_body=extra_body,
        )

        if not resp.data:
            return "Error: image generation returned no result."

        image_url = resp.data[0].url
        if not image_url:
            return "Error: image generation returned no URL."

        # 下载到临时文件 → 上传 Member Center 换公网 URL（云端为权威存储）
        data = await download_bytes(image_url)
        tmp_path = await write_temp(data, ".png")
        try:
            public_url = await evocloud_manager.api.upload_chat_media(tmp_path, "image")
        finally:
            await remove_file(tmp_path)

        # 结构化引用直传：AI 消息持久化时合并（不依赖模型复述链接）
        stash_media_ref("image", public_url, "generated image")

        return (
            f"![generated image]({public_url})\n\n"
            f"(图片已生成并上传。你的最终回复中无需重复该链接——界面会自动展示图片；"
            f"如需在正文中提及，请原样保留上面的图片链接。)"
        )
    except Exception as e:
        logger.exception(f"[Image] generate failed: {e}")
        return f"Error: image generation failed: {str(e)}"


