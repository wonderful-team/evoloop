import logging
import os
import time

from app.infrastructure.drivers.macos import macos_driver
from app.infrastructure.vision.providers.base import VisionProvider
from app.infrastructure.vision.types import (
    ElementType,
    UIElement,
    VisionResult,
    VisionTask,
)
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class MacOSVisionOCRProvider(VisionProvider):
    """
    Native MacOS OCR provider using Vision.framework.
    Requires pyobjc-framework-Vision.
    """

    @property
    def name(self) -> str:
        return "macos_vision_ocr"

    @property
    def cost_factor(self) -> float:
        return 0.0  # Completely free local processing

    async def is_available(self) -> bool:
        """Check if Vision framework is accessible."""
        import importlib.util

        return (
            importlib.util.find_spec("Quartz") is not None
            and importlib.util.find_spec("Vision") is not None
        )

    async def process(self, task: VisionTask, image_source: str, prompt: str | None = None, **kwargs) -> VisionResult:
        if task != VisionTask.OCR and task != VisionTask.DETECT:
            return VisionResult(
                task=task,
                success=False,
                metadata={
                    "error": f"Task {task} not supported by MacOSVisionOCRProvider"
                },
            )

        start_time = time.time()

        if not os.path.exists(image_source):
             return VisionResult(task=task, success=False, metadata={"error": "File not found"})

        try:
            import Foundation
            import Vision

            # Load image
            url = Foundation.NSURL.fileURLWithPath_(image_source)
            request_handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)

            elements = []

            # Create OCR request
            request = Vision.VNRecognizeTextRequest.alloc().init()
            # Set recognition level to Accurate for higher precision (Critical for UI elements)
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            # Support both English and Chinese if supported by OS
            try:
                request.setRecognitionLanguages_(["zh-Hans", "en-US"])
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

            # Perform request
            success, error = request_handler.performRequests_error_([request], None)
            if not success:
                return VisionResult(task=task, success=False, metadata={"error": str(error)})

            observations = request.results()

            # Get image size
            from PIL import Image

            with Image.open(image_source) as img:
                img_w, img_h = img.size

            # Get scale factor if this is a MacOS screenshot
            scale = self._get_ui_scale_factor(image_source)

            for i, observation in enumerate(observations):
                # getTopCandidates returns list of VNRecognizedText
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue

                text_obj = candidates[0]
                text_val = text_obj.string()
                confidence = text_obj.confidence()

                # Vision bbox: Origin (x, y) is bottom-left (normalized)
                bbox = observation.boundingBox()

                # Convert to pixel coordinates (0,0 at top left)
                # Vision bbox: Origin (x, y) is bottom-left
                w = int(bbox.size.width * img_w)
                h = int(bbox.size.height * img_h)
                x = int(bbox.origin.x * img_w)
                y = int((1.0 - bbox.origin.y - bbox.size.height) * img_h)

                # Normalize to Logical Points (Handle Retina scaling for MacOS)
                logical_x = (x + w // 2) / scale
                logical_y = (y + h // 2) / scale

                element = UIElement(
                    id=i,
                    text=text_val,
                    x=int(logical_x),
                    y=int(logical_y),
                    width=int(w / scale),
                    height=int(h / scale),
                    element_type=ElementType.TEXT,
                    confidence=float(confidence),
                    source=self.name,
                )
                elements.append(element)

            latency = elapsed_ms(start_time)
            result = VisionResult(
                task=task,
                success=True,
                elements=elements,
                summary=f"Extracted {len(elements)} elements using {self.name}.",
                screenshot_path=image_source,
                latency_ms=latency,
            )

            return result

        except Exception as e:
            logger.exception(f"{self.name} failed: {e}")
            return VisionResult(task=task, success=False, metadata={"error": str(e)})

    def _get_ui_scale_factor(self, image_source: str) -> float:
        """Get host-specific scale factor only if image is from macOS."""
        # Check if this is a macOS image by directory
        if "android" in image_source or "mobile" in image_source or "frames" in image_source:
             return 1.0

        # macOS ones from ~/.evoloop/artifacts/screenshots
        try:
            return macos_driver.get_ui_scale_factor()
        except Exception:
            return 1.0
