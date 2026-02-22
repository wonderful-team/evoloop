import logging
import os
import time

from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import ElementType, UIElement, VisionResult, VisionTask

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
_ocr_engine = None
_ocr_type = None


def _get_ocr_engine():
    """Lazy-load OCR engine with fallback."""
    global _ocr_engine, _ocr_type

    if _ocr_engine is not None:
        return _ocr_engine, _ocr_type

    # Try EasyOCR first (lighter weight)
    try:
        import easyocr
        _ocr_engine = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        _ocr_type = "easyocr"
        logger.info("LocalOCRProvider: Using EasyOCR")
        return _ocr_engine, _ocr_type
    except ImportError:
        pass

    # Try PaddleOCR
    try:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
        _ocr_type = "paddleocr"
        logger.info("LocalOCRProvider: Using PaddleOCR")
        return _ocr_engine, _ocr_type
    except ImportError:
        pass

    logger.debug("LocalOCRProvider: No external OCR library (EasyOCR/PaddleOCR) available. Falling back to native system providers.")
    return None, None


class LocalOCRProvider(VisionProvider):
    """
    Local OCR provider using EasyOCR or PaddleOCR.
    """

    @property
    def name(self) -> str:
        return "local_ocr"

    @property
    def cost_factor(self) -> float:
        return 0.1  # Low cost - local processing

    async def is_available(self) -> bool:
        engine, _ = _get_ocr_engine()
        return engine is not None

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: str | None = None,
        **kwargs
    ) -> VisionResult:
        """Process OCR task."""
        if task != VisionTask.OCR:
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": f"Task {task} not supported by LocalOCRProvider"}
            )

        start_time = time.time()

        if not image_source or not os.path.exists(image_source):
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": "Image file not found"}
            )

        engine, ocr_type = _get_ocr_engine()
        if engine is None:
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": "OCR engine not available"}
            )

        elements = []
        element_id = 0

        try:
            if ocr_type == "easyocr":
                results = engine.readtext(image_source)
                for bbox, text, confidence in results:
                    if confidence < 0.3:
                        continue

                    x1, y1 = bbox[0]
                    x2, y2 = bbox[2]

                    element = UIElement(
                        id=element_id,
                        text=text,
                        x=int((x1 + x2) / 2),
                        y=int((y1 + y2) / 2),
                        width=int(x2 - x1),
                        height=int(y2 - y1),
                        element_type=ElementType.TEXT,
                        confidence=float(confidence),
                        source=self.name,
                    )
                    elements.append(element)
                    element_id += 1

            elif ocr_type == "paddleocr":
                results = engine.ocr(image_source, cls=True)
                if results and results[0]:
                    for line in results[0]:
                        bbox, (text, confidence) = line
                        if confidence < 0.3:
                            continue

                        x1, y1 = bbox[0]
                        x2, y2 = bbox[2]

                        element = UIElement(
                            id=element_id,
                            text=text,
                            x=int((x1 + x2) / 2),
                            y=int((y1 + y2) / 2),
                            width=int(x2 - x1),
                            height=int(y2 - y1),
                            element_type=ElementType.TEXT,
                            confidence=float(confidence),
                            source=self.name,
                        )
                        elements.append(element)
                        element_id += 1

            success = True
            summary = f"Extracted {len(elements)} text elements using {ocr_type}."

        except Exception as e:
            logger.error(f"LocalOCRProvider process failed: {e}")
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": str(e)}
            )

        latency = (time.time() - start_time) * 1000

        return VisionResult(
            task=task,
            success=success,
            elements=elements,
            summary=summary,
            screenshot_path=image_source,
            latency_ms=latency,
            metadata={"ocr_type": ocr_type}
        )
