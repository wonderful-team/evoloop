import logging
import os
import subprocess
from typing import Literal, cast

logger = logging.getLogger(__name__)


class ScreenshotMixin:
    @staticmethod
    def screenshot(region=None, purpose="temp", bundle_id=None, suffix=None, interactive=False):
        from app.infrastructure.vision.storage import screenshot_storage

        filepath = screenshot_storage.get_path(
            purpose=cast(Literal["temp", "atlas", "debug", "dataset"], purpose),
            platform="macos",
            bundle_id=bundle_id,
            suffix=suffix,
        )

        if interactive:
            # 交互式区域截图：用户在屏幕上用鼠标拖拽框选区域。
            # `screencapture -i` 由 Python 原生执行（不经 AppleScript
            # `do shell script`），因此不触发 script_gate 的 shell 逃逸审查。
            # 用户按 Esc 取消时 returncode 非 0，且不会生成文件。
            cmd = ["screencapture", "-i", filepath]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(
                    "Interactive screenshot cancelled or failed "
                    f"(returncode={result.returncode}): {result.stderr.strip()}"
                )
            if not os.path.exists(filepath):
                raise RuntimeError("Screenshot file was not created")
            logger.info(f"Interactive screenshot saved: {filepath}")
            return filepath

        cmd = ["screencapture", "-x"]

        if region:
            try:
                x, y, w, h = map(int, region.split(","))
                cmd.extend(["-R", f"{x},{y},{w},{h}"])
            except ValueError:
                logger.warning(f"Invalid region format: {region}, capturing full screen", exc_info=True)

        cmd.append(filepath)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            raise RuntimeError(f"Screenshot failed: {result.stderr}")

        if not os.path.exists(filepath):
            raise RuntimeError("Screenshot file was not created")

        logger.info(f"Screenshot saved: {filepath}")
        return filepath
