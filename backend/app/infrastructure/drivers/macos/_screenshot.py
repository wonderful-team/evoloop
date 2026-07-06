import logging
import os
import subprocess
import time
from typing import Any, Literal, cast

logger = logging.getLogger(__name__)


class ScreenshotMixin:
    @staticmethod
    def screenshot(region=None, purpose="temp", bundle_id=None, suffix=None):
        from app.infrastructure.vision.storage import screenshot_storage
        filepath = screenshot_storage.get_path(
            purpose=cast(Literal["temp", "atlas", "debug", "dataset"], purpose),
            platform="macos",
            bundle_id=bundle_id,
            suffix=suffix,
        )

        cmd = ["screencapture", "-x"]

        if region:
            try:
                x, y, w, h = map(int, region.split(","))
                cmd.extend(["-R", f"{x},{y},{w},{h}"])
            except ValueError:
                logger.warning(f"Invalid region format: {region}, capturing full screen")

        cmd.append(filepath)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            raise RuntimeError(f"Screenshot failed: {result.stderr}")

        if not os.path.exists(filepath):
            raise RuntimeError("Screenshot file was not created")

        logger.info(f"Screenshot saved: {filepath}")
        return filepath
