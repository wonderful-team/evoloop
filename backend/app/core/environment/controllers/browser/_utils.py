"""
Browser controller shared utilities.
"""
import logging

from app.infrastructure.vision import VisionTask, vision_engine
from app.utils.controller_response import ControllerResponse

logger = logging.getLogger(__name__)


def _tmp_screenshot_path(
    purpose: str = "temp",
    bundle_id: str | None = None,
    suffix: str | None = None
) -> str:
    from app.infrastructure.vision.storage import screenshot_storage
    return screenshot_storage.get_path(
        purpose=purpose,
        platform="browser",
        bundle_id=bundle_id,
        suffix=suffix
    )


async def _run_ocr(filepath: str) -> str:
    try:
        ocr_result = await vision_engine.process(VisionTask.OCR, filepath, enable_atlas_learning=False)
        if ocr_result.success and ocr_result.elements:
            from app.utils.template import render_template
            return "\n\n" + render_template(
                "core/vision/ocr_results.prompt.j2",
                platform="browser",
                elements=[el.model_dump() for el in ocr_result.elements],
                total_count=len(ocr_result.elements)
            )
        return "\n\n" + ControllerResponse.error("OCR: no text detected")
    except Exception as e:
        logger.error(f"[Browser] OCR failed: {e}")
        return "\n\n" + ControllerResponse.error("OCR Error.", details=str(e))


def _resolve_selector(selector: str | None, text: str | None) -> str | None:
    if selector:
        return selector
    if text:
        return f"text={text}"
    return None
