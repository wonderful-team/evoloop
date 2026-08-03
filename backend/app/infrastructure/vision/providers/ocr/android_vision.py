import logging

from app.infrastructure.drivers.adb import adb_driver
from app.infrastructure.vision.providers.ocr.macos_vision import MacOSVisionOCRProvider

logger = logging.getLogger(__name__)


class AndroidVisionOCRProvider(MacOSVisionOCRProvider):
    """
    Specialized Android OCR provider that utilizes MacOS Vision.framework
    but handles Android-specific coordinate scaling (pixel-perfect, no logical scaling).
    """

    @property
    def name(self) -> str:
        return "android_vision_ocr"

    async def is_available(self) -> bool:
        """
        Check if both MacOS Vision is available AND an Android device is connected.
        """
        vision_avail = await super().is_available()
        if not vision_avail:
            return False

        try:
            devices = adb_driver.list_devices()
            return any(d["status"] == "device" for d in devices)
        except Exception:
            return False

    def _get_ui_scale_factor(self, image_source: str | None = None) -> float:
        """
        Override: Android screenshots are pixel-absolute, so we use a scale of 1.0.
        Unlike MacOS screenshots which need to be converted to logical points.
        """
        return 1.0
