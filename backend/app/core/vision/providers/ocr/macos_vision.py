import logging
import os
import time

from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import ElementType, UIElement, VisionResult, VisionTask

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
        try:
            import Quartz
            import Vision
            return True
        except ImportError:
            return False

    async def process(
        self,
        task: VisionTask,
        image_source: str,
        prompt: str | None = None,
        **kwargs
    ) -> VisionResult:
        if task != VisionTask.OCR and task != VisionTask.DETECT:
            return VisionResult(
                task=task,
                success=False,
                metadata={"error": f"Task {task} not supported by MacOSVisionOCRProvider"}
            )

        start_time = time.time()

        if not os.path.exists(image_source):
             return VisionResult(task=task, success=False, metadata={"error": "File not found"})

        try:
            import Vision
            from Cocoa import NSURL

            # Load image
            url = NSURL.fileURLWithPath_(image_source)
            request_handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)

            elements = []

            # Create OCR request
            request = Vision.VNRecognizeTextRequest.alloc().init()
            # Set recognition level to accurate (better for UI)
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            # Support both English and Chinese if supported by OS
            try:
                request.setRecognitionLanguages_(["zh-Hans", "en-US"])
            except:
                pass

            # Perform request
            success, error = request_handler.performRequests_error_([request], None)

            if not success:
                return VisionResult(task=task, success=False, metadata={"error": str(error)})

            observations = request.results()

            # Get image size to convert normalized coordinates
            # We can get this from the image metadata or use macos_driver
            # For simplicity, we assume the screenshot is full screen or we get dimensions from file
            from PIL import Image
            with Image.open(image_source) as img:
                img_w, img_h = img.size

            for i, observation in enumerate(observations):
                # getTopCandidates returns list of VNRecognizedText
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue

                text_obj = candidates[0]
                text_val = text_obj.string()
                confidence = text_obj.confidence()

                # boundingBox is normalized (0,0 at bottom left)
                bbox = observation.boundingBox()

                # Convert to pixel coordinates (0,0 at top left)
                # Vision bbox: Origin (x, y) is bottom-left
                w = int(bbox.size.width * img_w)
                h = int(bbox.size.height * img_h)
                x = int(bbox.origin.x * img_w)
                y = int((1.0 - bbox.origin.y - bbox.size.height) * img_h)

                element = UIElement(
                    id=i,
                    text=text_val,
                    x=x + w // 2,
                    y=y + h // 2,
                    width=w,
                    height=h,
                    element_type=ElementType.TEXT,
                    confidence=float(confidence),
                    source=self.name
                )
                elements.append(element)

            latency = (time.time() - start_time) * 1000
            return VisionResult(
                task=task,
                success=True,
                elements=elements,
                summary=f"Extracted {len(elements)} text elements using MacOS Vision.",
                screenshot_path=image_source,
                latency_ms=latency
            )

        except Exception as e:
            logger.error(f"MacOSVisionOCRProvider failed: {e}")
            return VisionResult(task=task, success=False, metadata={"error": str(e)})
