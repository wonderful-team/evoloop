"""
Desktop controller mixin — tri-engine element resolution (AX + Atlas + OCR).
"""
import asyncio
import logging
import time

from app.core.atlas import atlas_engine
from app.core.environment.schemas import ElementResolutionResult
from app.core.file import cleanup_file
from app.infrastructure.vision import VisionTask, vision_engine
from app.infrastructure.drivers.macos import macos_driver
from app.utils.controller_response import ControllerResponse
from app.utils.text import normalize_text

from ._utils import _async_literal_eval

logger = logging.getLogger(__name__)


class DesktopElementMixin:

    @classmethod
    async def _try_ax_tree(cls, name: str, role: str | None = None) -> ElementResolutionResult | None:
        try:
            raw_tree = await asyncio.wait_for(
                asyncio.to_thread(macos_driver.dump_ax_tree),
                timeout=3.0
            )
            if not raw_tree or "Error" in raw_tree:
                return None

            elements = await _async_literal_eval(raw_tree.replace("missing value", "None"))
            target_norm = normalize_text(name)
            candidates = []

            for el in elements:
                el_name = normalize_text(el.get("name", ""))
                el_role = str(el.get("role", "")).lower()
                if el_name == target_norm:
                    score = 100
                elif target_norm in el_name:
                    score = 50
                else:
                    continue
                if role and role.lower() in el_role:
                    score += 10
                candidates.append((score, el))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                best_el = candidates[0][1]
                res = ElementResolutionResult()
                if "path" in best_el:
                    res.type = "path"
                    res.value = best_el["path"]
                bounds = best_el.get("bounds", [])
                if len(bounds) == 4:
                    res.x = int(bounds[0] + bounds[2] / 2)
                    res.y = int(bounds[1] + bounds[3] / 2)
                    if res.type is None:
                        res.type = "coords"
                if res.type or res.value or res.x is not None:
                    logger.debug(f"[Desktop] AX Tree resolved '{name}': {res.model_dump()}")
                    return res
            return None
        except asyncio.TimeoutError:
            logger.debug(f"[Desktop] AX Tree timeout for '{name}'")
            return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"[Desktop] AX Tree failed for '{name}': {e}")
            return None

    @classmethod
    async def _try_atlas(cls, name: str) -> ElementResolutionResult | None:
        try:
            app_info = await asyncio.to_thread(macos_driver.get_current_app)
            bundle_id = app_info.get("bundle_id")
            if not bundle_id:
                return None

            result = await atlas_engine.resolve_spatial_element(bundle_id, name, platform="macos")
            if result:
                if "x" in result and "y" in result:
                    return ElementResolutionResult(x=result["x"], y=result["y"], source=result.get("source", "atlas"))
                elif "strategy" in result:
                    return ElementResolutionResult(
                        strategy=result["strategy"],
                        parameters=result.get("parameters", {}),
                        source=result.get("source", "atlas_strategy")
                    )
            return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"[Desktop] Atlas resolution dividend failed: {e}")
            return None

    @classmethod
    async def _try_ocr(cls, name: str) -> ElementResolutionResult | None:
        temp_img = None
        try:
            app_info = await asyncio.to_thread(macos_driver.get_current_app)
            bounds_str = app_info.get("bounds")
            win_x, win_y = 0, 0

            if bounds_str:
                try:
                    win_x, win_y, _, _ = map(int, bounds_str.split(","))
                    temp_img = await asyncio.to_thread(macos_driver.screenshot, region=bounds_str)
                except ValueError:
                    temp_img = await asyncio.to_thread(macos_driver.screenshot)
            else:
                temp_img = await asyncio.to_thread(macos_driver.screenshot)

            result = await asyncio.wait_for(
                vision_engine.process(VisionTask.OCR, temp_img),
                timeout=5.0
            )

            target_name = normalize_text(name)
            if result.success:
                for el in result.elements:
                    if target_name in normalize_text(el.text):
                        logger.info(f"[Desktop] OCR resolved '{name}' \u2192 ({win_x + el.x}, {win_y + el.y})")
                        return ElementResolutionResult(type="coords", x=win_x + el.x, y=win_y + el.y)
            return None
        except asyncio.TimeoutError:
            logger.debug(f"[Desktop] OCR timeout for '{name}'")
            return None
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug(f"[Desktop] OCR failed for '{name}': {e}")
            return None
        finally:
            if temp_img:
                cleanup_file(temp_img)

    @classmethod
    async def _resolve_element(cls, name: str, role: str | None = None) -> ElementResolutionResult | str:
        logger.info(f"[Desktop] Resolving element '{name}' with parallel tri-engine...")
        start_time = time.time()

        ax_task = asyncio.create_task(cls._try_ax_tree(name, role))
        atlas_task = asyncio.create_task(cls._try_atlas(name))
        ocr_task = asyncio.create_task(cls._try_ocr(name))

        pending = {ax_task, atlas_task, ocr_task}
        result = None
        completed_sources = []

        while pending:
            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED
            )

            for task in done:
                try:
                    res = task.result()
                    if task == ax_task:
                        completed_sources.append("AX")
                    elif task == atlas_task:
                        completed_sources.append("Atlas")
                    else:
                        completed_sources.append("OCR")

                    if res:
                        result = res
                        for p in pending:
                            p.cancel()
                        break
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.debug(f"[Desktop] Engine task failed: {e}")

            if result:
                break

        elapsed = time.time() - start_time

        if result:
            logger.info(f"[Desktop] Resolved '{name}' via {completed_sources[-1]} in {elapsed:.2f}s")
            return result

        logger.error(f"[Desktop] Failed to resolve '{name}' after {elapsed:.2f}s (tried: {completed_sources})")
        return ControllerResponse.error(f"Could not resolve element '{name}'")
