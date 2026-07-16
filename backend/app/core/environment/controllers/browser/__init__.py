"""
Browser Controller — Core Playwright-based browser automation.

Extracted from app.domain.tools.environment.browser to allow:
  1. Direct invocation by MacroEngine without @evoloop_tool overhead.
  2. Clean separation between capability logic (here) and Agent-facing
     tool interface (domain/tools/environment/browser.py thin wrapper).
"""
import logging
import os
import time
from typing import Any

from app.core.context import ContextManager
from app.core.environment.controllers.utils import (
    BatchExecutor,
    RecordingContext,
)
from app.core.learning.trace_recorder import get_recorder
from app.infrastructure.drivers.browser import browser_manager
from app.utils.controller_response import ControllerResponse

from ._advanced import BrowserAdvancedMixin
from ._extraction import BrowserExtractionMixin
from ._interaction import BrowserInteractionMixin
from ._navigation import BrowserNavigationMixin
from ._perception import BrowserPerceptionMixin
from ._utils import _resolve_selector

logger = logging.getLogger(__name__)


class BrowserController(
    BrowserNavigationMixin,
    BrowserInteractionMixin,
    BrowserExtractionMixin,
    BrowserPerceptionMixin,
    BrowserAdvancedMixin,
):
    """
    Core browser automation logic via Playwright.

    All methods are classmethods (stateless) — browser state lives in
    the singleton `browser_manager` from infrastructure.
    """

    @classmethod
    async def execute(
        cls,
        action: str,
        url: str | None = None,
        tab_index: int | None = None,
        selector: str | None = None,
        text: str | None = None,
        value: str | None = None,
        key: str | None = None,
        source_selector: str | None = None,
        target_selector: str | None = None,
        direction: str | None = None,
        amount: int = 300,
        clear_first: bool = True,
        full_page: bool = False,
        ocr: bool = False,
        attribute: str | None = None,
        state: str = "visible",
        url_pattern: str | None = None,
        timeout_ms: int = 15_000,
        cookies: list[dict] | None = None,
        storage_action: str | None = None,
        storage_key: str | None = None,
        dialog_action: str | None = None,
        dialog_text: str | None = None,
        script: str | None = None,
        x: int | None = None,
        y: int | None = None,
        actions: list[dict] | None = None,
        continue_on_error: bool = True,
        delay_ms: int = 100,
        file_path: str | None = None,
        **kwargs: Any
    ) -> str:
        try:
            # ── Lifecycle ──────────────────────────────────────────────────
            if action == "close":
                await browser_manager.close()
                return ControllerResponse.success("Browser closed.")

            if action == "new_tab":
                page = await browser_manager.new_tab(url)
                count = browser_manager.tab_count()
                return ControllerResponse.success(f"New tab opened (tab {count - 1}/{count - 1}). URL: {page.url}")

            if action == "switch_tab":
                if tab_index is None:
                    return ControllerResponse.missing_param("tab_index")
                page = await browser_manager.switch_tab(tab_index)
                return ControllerResponse.success(f"Switched to tab {tab_index}. URL: {page.url}")

            # ── All other actions need a live page ────────────────────────
            page = await browser_manager.get_page()

            # Phase 5: Imitation Learning - Trace Recording
            thread_id = ContextManager.get_var("thread_id") or "default"
            recorder = get_recorder(thread_id)
            recording_ctx = RecordingContext(
                platform="web",
                recorder=recorder,
                screenshot_actions=("click", "type_text", "navigate", "submit")
            )

            async def _record(action_type: str, params: dict):
                async def screenshot_fn():
                    return await page.screenshot(animations="disabled")

                async def context_fn():
                    return {"url": page.url, "title": await page.title()}

                await recording_ctx.record(action_type, params, screenshot_fn, context_fn)

            pre_url = page.url
            try:
                pre_title = await page.title()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError):
                pre_title = ""

            # ── Build shared context dict for mixin handlers ──────────────
            ctx = {
                "page": page,
                "recording_func": _record,
                "pre_url": pre_url,
                "pre_title": pre_title,
                "url": url,
                "tab_index": tab_index,
                "selector": selector,
                "text": text,
                "value": value,
                "key": key,
                "source_selector": source_selector,
                "target_selector": target_selector,
                "direction": direction,
                "amount": amount,
                "clear_first": clear_first,
                "full_page": full_page,
                "ocr": ocr,
                "attribute": attribute,
                "state": state,
                "url_pattern": url_pattern,
                "timeout_ms": timeout_ms,
                "cookies": cookies,
                "storage_action": storage_action,
                "storage_key": storage_key,
                "dialog_action": dialog_action,
                "dialog_text": dialog_text,
                "script": script,
                "x": x,
                "y": y,
                "actions": actions,
                "continue_on_error": continue_on_error,
                "delay_ms": delay_ms,
                "file_path": file_path,
                "kwargs": kwargs,
            }

            # ── Dispatch to mixin handlers ────────────────────────────────
            if action in ("navigate", "back", "forward", "reload", "get_url"):
                result = await cls._handle_navigation(action, **ctx)
                if result is not None:
                    return result

            elif action in ("click", "double_click", "hover", "type_text", "select_option",
                            "key_press", "scroll", "drag_drop"):
                result = await cls._handle_interaction(action, **ctx)
                if result is not None:
                    return result

            elif action in ("get_text", "get_html", "get_attribute", "get_links",
                            "find_element", "get_elements"):
                result = await cls._handle_extraction(action, **ctx)
                if result is not None:
                    return result

            elif action in ("screenshot", "wait_for", "check_element"):
                result = await cls._handle_perception(action, **ctx)
                if result is not None:
                    return result

            elif action in ("run_js", "get_cookies", "set_cookies", "local_storage",
                            "network_wait", "wait_for_stability", "dialog_handle",
                            "scroll_to_bottom", "detect_pagination"):
                result = await cls._handle_advanced(action, **ctx)
                if result is not None:
                    return result

            # ── Batch & File (stay in __init__ for recursion) ────────────
            if action == "batch":
                if not actions:
                    return ControllerResponse.missing_param("actions")

                batch_start = time.time()
                executor = BatchExecutor(continue_on_error=continue_on_error, delay_ms=delay_ms)

                async def _exec_action(action_dict: dict) -> str:
                    params = {k: v for k, v in action_dict.items() if k != "action" and v is not None}
                    return await cls.execute(action=action_dict.get("action", "unknown"), **params)

                await executor.execute(actions, _exec_action)
                return executor.format_summary(time.time() - batch_start)

            elif action == "upload":
                if not file_path:
                    return ControllerResponse.missing_param("file_path")
                if not os.path.isfile(file_path):
                    return ControllerResponse.not_found(file_path, item_type="file")
                loc = _resolve_selector(selector, text)
                if not loc:
                    return ControllerResponse.missing_param("selector or text")
                try:
                    await page.locator(loc).first.set_input_files(file_path)
                    return ControllerResponse.success(f"Uploaded file '{os.path.basename(file_path)}' to {loc}")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                    logger.error(f"[Browser] Upload failed: {e}")
                    return ControllerResponse.error("Upload failed.", details=str(e))

            else:
                return ControllerResponse.error(f"Unknown action '{action}'.")

        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
            error_msg = f"[Browser] action='{action}' failed: {e}"
            if continue_on_error:
                logger.warning(f"Optional {error_msg}. Continuing.")
                return ControllerResponse.success("Optional action failed, continuing.", details=str(e))
            logger.error(error_msg, exc_info=True)
            return ControllerResponse.error(f"Action failed: {action}", details=str(e))
