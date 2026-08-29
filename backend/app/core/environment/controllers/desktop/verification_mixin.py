"""
Desktop controller mixin — UI verification actions.
"""

import asyncio
import logging
import time

from app.infrastructure.drivers.macos import macos_driver
from app.utils.controller_response import ControllerResponse

from .utils import _async_literal_eval

logger = logging.getLogger(__name__)


class DesktopVerificationMixin:
    @classmethod
    async def verify_ui_state(
        cls,
        expected_element: str | None = None,
        expected_role: str | None = None,
        expected_text: str | None = None,
        timeout_seconds: int = 0,
    ) -> str:
        async def _check_once():
            raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
            if not raw_tree or "Error" in raw_tree:
                return (False, False), ControllerResponse.error(
                    "Verification Failed: Could not dump AX Tree.",
                    details=str(raw_tree),
                )
            elements = await _async_literal_eval(raw_tree)
            found_element = False
            found_text = False
            for el in elements:
                name = str(el.get("name", "")).lower()
                role = str(el.get("role", "")).lower()
                value = str(el.get("value", "")).lower()
                if expected_element and expected_element.lower() in name:
                    if not expected_role or expected_role.lower() in role:
                        found_element = True
                if expected_text and (
                    expected_text.lower() in name or expected_text.lower() in value
                ):
                    found_text = True
            return (found_element, found_text), None

        try:
            if timeout_seconds <= 0:
                (found_element, found_text), err = await _check_once()
                if err:
                    return err
                if expected_element and not found_element:
                    return ControllerResponse.error(
                        f"Verification FAILED: Element '{expected_element}'"
                        + (f" (role: {expected_role})" if expected_role else "")
                        + " not found."
                    )
                if expected_text and not found_text:
                    return ControllerResponse.error(
                        f"Verification FAILED: Text '{expected_text}' not found."
                    )
                return ControllerResponse.success(
                    "Verification SUCCESS: UI state matches expectations."
                )

            start = asyncio.get_running_loop().time()
            while True:
                (found_element, found_text), err = await _check_once()
                if err:
                    return err
                if (not expected_element or found_element) and (
                    not expected_text or found_text
                ):
                    return ControllerResponse.success(
                        "Verification SUCCESS: UI state matches expectations."
                    )
                if asyncio.get_running_loop().time() - start >= timeout_seconds:
                    if expected_element and not found_element:
                        return ControllerResponse.error(
                            f"Verification FAILED: Element '{expected_element}'"
                            + (f" (role: {expected_role})" if expected_role else "")
                            + " not found."
                        )
                    if expected_text and not found_text:
                        return ControllerResponse.error(
                            f"Verification FAILED: Text '{expected_text}' not found."
                        )
                await asyncio.sleep(0.5)
        except Exception as e:
            return ControllerResponse.error("Verification Error.", details=str(e))

    @classmethod
    async def quick_check_screen(
        cls,
        check_type: str,
        target: str | None = None,
        timeout_seconds: int = 5,
    ) -> str:
        start_time = time.time()
        check_start = time.time()
        while time.time() - check_start < timeout_seconds:
            try:
                raw_tree = await asyncio.to_thread(macos_driver.dump_ax_tree)
                if not raw_tree or "Error" in raw_tree:
                    await asyncio.sleep(0.5)
                    continue
                try:
                    elements = await _async_literal_eval(
                        raw_tree.replace("missing value", "None")
                    )
                except Exception:
                    await asyncio.sleep(0.5)
                    continue
                if check_type == "is_loaded":
                    if len(elements) > 3:
                        elapsed = time.time() - start_time
                        return ControllerResponse.success(
                            f"Screen appears loaded ({len(elements)} elements)",
                            details=f"Elapsed: {elapsed:.2f}s",
                        )
                elif check_type == "has_text" and target:
                    target_lower = target.lower()
                    for el in elements:
                        if (
                            target_lower in str(el.get("name", "")).lower()
                            or target_lower in str(el.get("value", "")).lower()
                        ):
                            return ControllerResponse.success(
                                f"Found text '{target}' on screen",
                                details=f"Elapsed: {time.time() - start_time:.2f}s",
                            )
                elif check_type == "has_element" and target:
                    target_lower = target.lower()
                    for el in elements:
                        if target_lower in str(el.get("name", "")).lower():
                            bounds = el.get("bounds", [])
                            if len(bounds) == 4:
                                ex, ey = (
                                    int(bounds[0] + bounds[2] / 2),
                                    int(bounds[1] + bounds[3] / 2),
                                )
                                return ControllerResponse.success(
                                    f"Found element '{target}' at ({ex}, {ey})",
                                    details=f"Elapsed: {time.time() - start_time:.2f}s",
                                )
                            return ControllerResponse.success(
                                f"Found element '{target}'",
                                details=f"Elapsed: {time.time() - start_time:.2f}s",
                            )
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"[QuickCheck] Error: {e}", exc_info=True)
                await asyncio.sleep(0.5)
        elapsed = time.time() - start_time
        if check_type == "is_loaded":
            return ControllerResponse.error(
                f"Screen may not be fully loaded after {elapsed:.1f}s"
            )
        return ControllerResponse.error(f"Did not find '{target}' after {elapsed:.1f}s")
