import hashlib
import logging
import os
import time
from typing import Dict, Tuple

from app.core.vision.providers.base import VisionProvider
from app.core.vision.types import ElementType, UIElement, VisionResult, VisionTask

logger = logging.getLogger(__name__)


class MacOSVisionOCRProvider(VisionProvider):
    """
    Native MacOS OCR provider using Vision.framework.
    Includes result caching for performance.
    """

    # Cache for OCR results: (image_hash, task) -> (VisionResult, timestamp)
    _ocr_cache: Dict[Tuple[str, str], Tuple[VisionResult, float]] = {}
    _cache_ttl: float = 10.0  # Cache for 10 seconds (screen content changes frequently)
    _cache_max_size: int = 20

    @classmethod
    def _get_image_hash(cls, image_path: str) -> str:
        """Generate quick hash of image for caching."""
        try:
            with open(image_path, 'rb') as f:
                # Sample first and last 4KB for quick hash
                head = f.read(4096)
                f.seek(-4096, 2)
                tail = f.read(4096)
                return hashlib.md5(head + tail).hexdigest()[:16]
        except Exception:
            return ""

    @classmethod
    def _check_cache(cls, image_hash: str, task: str) -> VisionResult | None:
        """Check if we have a cached OCR result."""
        cache_key = (image_hash, task)
        if cache_key in cls._ocr_cache:
            result, timestamp = cls._ocr_cache[cache_key]
            if time.time() - timestamp < cls._cache_ttl:
                logger.debug(f"[OCR] Cache hit for image {image_hash[:8]}")
                # Return copy with updated metadata
                result.latency_ms = 0
                result.metadata["cached"] = True
                return result
            else:
                del cls._ocr_cache[cache_key]
        return None

    @classmethod
    def _store_cache(cls, image_hash: str, task: str, result: VisionResult) -> None:
        """Store OCR result in cache."""
        cache_key = (image_hash, task)
        cls._ocr_cache[cache_key] = (result, time.time())
        # Limit cache size
        if len(cls._ocr_cache) > cls._cache_max_size:
            oldest = min(cls._ocr_cache.keys(), key=lambda k: cls._ocr_cache[k][1])
            del cls._ocr_cache[oldest]
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

        # Check cache first
        image_hash = self._get_image_hash(image_source)
        if image_hash:
            cached = self._check_cache(image_hash, task.value)
            if cached:
                return cached

        try:
            import Vision
            from Cocoa import NSURL

            # Load image
            url = NSURL.fileURLWithPath_(image_source)
            request_handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)

            elements = []

            # Create OCR request
            request = Vision.VNRecognizeTextRequest.alloc().init()
            # Set recognition level to Accurate for higher precision (Critical for UI elements)
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
            
            # Get scale factor if this is a MacOS screenshot
            from app.infrastructure.drivers.macos import macos_driver
            scale = macos_driver.get_ui_scale_factor()

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

                # Normalize to Logical Points (Quartz coordinates)
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
                    source=self.name
                )
                elements.append(element)

            latency = (time.time() - start_time) * 1000
            result = VisionResult(
                task=task,
                success=True,
                elements=elements,
                summary=f"Extracted {len(elements)} text elements using MacOS Vision.",
                screenshot_path=image_source,
                latency_ms=latency
            )

            # Store in cache
            if image_hash:
                self._store_cache(image_hash, task.value, result)

            return result

        except Exception as e:
            logger.error(f"MacOSVisionOCRProvider failed: {e}")
            return VisionResult(task=task, success=False, metadata={"error": str(e)})
