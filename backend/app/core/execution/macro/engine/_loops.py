import asyncio
import json
import logging
import os
from datetime import datetime

from app.core.execution.macro.schemas import MacroSource
from app.core.monitoring.activity import activity_monitor
from app.utils.geometry import parse_bounds

logger = logging.getLogger(__name__)


class LoopMixin:
    @classmethod
    async def _handle_loop(cls, thread_id, step, payload, params, extracted_data, disable_ocr=True, active_bundle_id=None, execution_warnings=None):
        items_key = payload.get("items_key", "items")
        items = extracted_data.get(items_key) or params.get(items_key)

        if not items or not isinstance(items, list):
            lists = {k: v for k, v in extracted_data.items() if isinstance(v, list)}
            if len(lists) == 1:
                items_key = list(lists.keys())[0]
                items = lists[items_key]
                logger.info(f"[{thread_id}] Using fuzzy match for loop: key '{items_key}' found instead of '{payload.get('items_key')}'")
                await activity_monitor.log_event("macro_thought", {"text": f"Using fuzzy match: '{items_key}'"}, thread_id)
            else:
                warn_msg = f"[WARNING] Batch loop skipped: No items found for key '{items_key}'"
                logger.warning(f"[{thread_id}] {warn_msg}")
                await activity_monitor.log_event("macro_thought", {"text": warn_msg}, thread_id)
                if execution_warnings is not None:
                    execution_warnings.append(f"loop step {step.step_number} 迭代 0 次（items_key '{items_key}' 无数据）")
                return True, "", None

        logger.info(f"[{thread_id}] Starting Batch Loop: {len(items)} items for key '{items_key}'")
        await activity_monitor.log_event("macro_thought", {"text": f"Starting loop ({len(items)} items)"}, thread_id)

        is_dynamic = False
        bundle_id = None
        if step.source == MacroSource.MOBILE:
            try:
                from app.core.context.manager import ContextManager
                from app.core.environment.controllers.mobile import MobileController
                from app.core.environment.explorers.dynamic_apps import DynamicAppTriage
                from app.infrastructure.drivers.adb import adb_driver

                device_id = ContextManager.get_var("device_id")
                curr_app = await asyncio.to_thread(adb_driver.get_current_app, device_id=device_id)
                bundle_id = curr_app.get("package")
                if bundle_id:
                    dynamic_apps = await DynamicAppTriage.get_dynamic_apps(platform="android")
                    is_dynamic = bundle_id in dynamic_apps
            except Exception as e:
                logger.warning(f"Failed to detect dynamic status: {e}", exc_info=True)

        max_retries = payload.get("max_retries", 3)
        backoff_base = payload.get("backoff_base", 2)

        dlq = []

        for index, item in enumerate(items):
            retry_count = 0
            success = False
            last_error = ""

            scroll_attempts = 1 if is_dynamic else 0
            current_scroll_attempt = 0

            while retry_count <= max_retries:
                try:
                    iter_params = dict(params or {})
                    iter_params["item"] = item
                    iter_params["batch_index"] = index

                    success, msg, fallback = await cls.execute_steps(thread_id, step.steps, iter_params, extracted_data, disable_ocr, active_bundle_id, execution_warnings=execution_warnings)

                    if success:
                        break

                    last_error = msg
                    is_network_error = any(kw in msg.lower() for kw in ["network", "timeout", "connection", "http", "status 50", "429"])

                    if is_network_error:
                        sleep_time = backoff_base ** retry_count
                        logger.warning(f"[{thread_id}] Network error in batch iteration {index}. Retrying in {sleep_time}s... Error: {msg}")
                        await asyncio.sleep(sleep_time)
                        retry_count += 1
                    elif "ERR_ELEMENT_NOT_FOUND" in msg and current_scroll_attempt < scroll_attempts:
                        from app.core.environment.controllers.mobile import (
                            MobileController,
                        )

                        logger.info(f"[{thread_id}] Element not found in dynamic app. Attempting autonomous scroll...")
                        await MobileController.execute(action="swipe", direction="up", duration_ms=800)
                        await asyncio.sleep(1)
                        current_scroll_attempt += 1
                        continue
                    else:
                        logger.error(f"[{thread_id}] Functional error in batch iteration {index}: {msg}")
                        return False, msg, fallback

                except Exception as e:
                    last_error = str(e)
                    logger.exception(f"[{thread_id}] Unexpected error in batch iteration {index}: {e}")
                    retry_count += 1
                    await asyncio.sleep(backoff_base ** retry_count)

            if not success:
                logger.error(f"[{thread_id}] Batch item {index} failed after {max_retries} retries. Moving to DLQ.")
                dlq.append({"item": item, "error": last_error, "index": index})

        if dlq:
            logger.error(f"[{thread_id}] Batch completed with {len(dlq)} errors in DLQ: {dlq}")
            return True, f"Completed with {len(dlq)} items in DLQ", {"dlq": dlq}

        return True, "", None

    @classmethod
    async def _handle_collect_loop(
        cls,
        thread_id,
        step,
        payload,
        params,
        extracted_data,
        disable_ocr,
        collect_mode,
        active_bundle_id=None,
        execution_warnings=None,
    ):
        state_file = payload.get("state_file", f"/tmp/macro_collect_{thread_id}.json")
        list_config = payload.get("list_config", {})
        detail_config = payload.get("detail_config", {})

        state = {"items": [], "phase": "list", "created_at": datetime.now().isoformat()}
        if os.path.exists(state_file):
            try:
                with open(state_file, encoding='utf-8') as f:
                    state = json.load(f)
            except Exception as e:
                logger.warning(f"[{thread_id}] Failed to load state file, starting fresh: {e}", exc_info=True)

        if (collect_mode in ("list", "auto")) and (state["phase"] == "list" or collect_mode == "list"):
            logger.info(f"[{thread_id}] Starting LIST phase for batch collection")
            await activity_monitor.log_event("macro_thought", {"text": "Starting list collection phase"}, thread_id)

            max_screens = int(list_config.get("max_screens") or 10)
            swipe_distance = int(list_config.get("swipe_distance") or 1200)
            wait_ms = int(list_config.get("wait_after_swipe_ms") or 1500)

            anchor_rule = list_config.get("anchor_element", {"type": "price", "pattern": "￥[0-9,.]+"})
            feature_config = list_config.get("feature_region", {"offset_y": -200, "height": 200, "max_features": 4})

            seen_signatures = {item["signature"] for item in state["items"]}
            new_items_count = 0

            for screen_num in range(max_screens):
                logger.info(f"[{thread_id}] Collecting screen {screen_num + 1}/{max_screens}")

                try:
                    if step.source == MacroSource.MOBILE:
                        from app.infrastructure.drivers.adb import adb_driver
                        device_id = params.get("device_id")
                        xml = await asyncio.to_thread(adb_driver.dump_ui, device_id, compressed=False)
                    else:
                        raise NotImplementedError(f"Collect mode not implemented for source: {step.source}")
                except Exception as e:
                    logger.exception(f"[{thread_id}] Failed to get UI dump: {e}")
                    break

                items = cls._extract_collect_items_from_xml(xml, anchor_rule, feature_config)

                for item in items:
                    if item["signature"] not in seen_signatures:
                        seen_signatures.add(item["signature"])
                        item["status"] = "pending"
                        item["collected_at"] = datetime.now().isoformat()
                        item["screen_num"] = screen_num + 1
                        state["items"].append(item)
                        new_items_count += 1

                logger.info(f"[{thread_id}] Screen {screen_num + 1}: found {len(items)}, new {new_items_count}")

                if screen_num >= max_screens - 1:
                    break

                try:
                    from app.core.environment.controllers.mobile import MobileController

                    scroll_ratio = min(0.9, max(0.1, swipe_distance / 2400.0 if swipe_distance > 1 else 0.5))

                    res = await MobileController.execute(
                        action="scroll",
                        direction="down",
                        scroll_amount=scroll_ratio,
                        device_id=params.get("device_id"),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        expected_pkg=active_bundle_id
                    )

                    if isinstance(res, str) and (res.startswith("Error") or res.startswith("ERR_")):
                        logger.error(f"[{thread_id}] Scroll failed: {res}")
                        break

                    await asyncio.sleep(wait_ms / 1000)
                except Exception as e:
                    logger.exception(f"[{thread_id}] Scroll action exception: {e}")
                    break

            state["phase"] = "detail"
            state["updated_at"] = datetime.now().isoformat()
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            logger.info(f"[{thread_id}] LIST phase complete: {len(state['items'])} items collected")
            await activity_monitor.log_event("macro_thought", {"text": f"List collection complete: {len(state['items'])} items"}, thread_id)

            if collect_mode == "list":
                extracted_data["collected_items"] = state["items"]
                extracted_data["collect_state_file"] = state_file
                return True, f"List collection complete: {len(state['items'])} items", {"state_file": state_file}

        if collect_mode in ("detail", "auto") and state["phase"] in ("detail", "completed"):
            logger.info(f"[{thread_id}] Starting DETAIL phase for batch collection")
            await activity_monitor.log_event("macro_thought", {"text": "Starting detail execution phase"}, thread_id)

            pending_items = [item for item in state["items"] if item.get("status") == "pending"]
            if not pending_items:
                logger.info(f"[{thread_id}] No pending items to process")
                return True, "No pending items", None

            limit = int(detail_config.get("limit") or 0)
            if limit:
                pending_items = pending_items[:limit]

            success_count = 0
            fail_count = 0

            for i, item in enumerate(pending_items):
                logger.info(f"[{thread_id}] Processing item {i+1}/{len(pending_items)}: {item['signature'][:50]}")

                try:
                    from app.core.environment.controllers.mobile import MobileController

                    tap_x = item.get("tap_x", 540)
                    tap_y = item.get("tap_y", item.get("anchor_y", 500))

                    await MobileController.execute(
                        action="click",
                        x=tap_x,
                        y=tap_y,
                        device_id=params.get("device_id"),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        expected_pkg=active_bundle_id
                    )
                    await asyncio.sleep(detail_config.get("wait_after_tap_ms", 2000) / 1000)

                    if step.steps:
                        iter_params = dict(params)
                        iter_params["item"] = item
                        iter_params["item_index"] = i
                        iter_params["collected_signature"] = item["signature"]

                        success, msg, fallback = await cls.execute_steps(
                            thread_id,
                            step.steps,
                            iter_params,
                            extracted_data,
                            disable_ocr,
                            active_bundle_id,
                            execution_warnings=execution_warnings
                        )

                        if not success:
                            logger.warning(f"[{thread_id}] Detail steps failed for item {i}: {msg}")
                            item["status"] = "failed"
                            item["error"] = msg
                            fail_count += 1
                        else:
                            item["status"] = "done"
                            item["completed_at"] = datetime.now().isoformat()

                            capture_config = detail_config.get("data_capture")
                            if capture_config:
                                for target_key, source_key in capture_config.items():
                                    val = extracted_data.get(source_key)
                                    if val is not None:
                                        item[target_key] = val
                                logger.info(f"[{thread_id}] Captured {len(capture_config)} fields into item {i}")

                            success_count += 1
                    else:
                        item["status"] = "done"
                        item["completed_at"] = datetime.now().isoformat()
                        success_count += 1

                    from app.core.environment.controllers.mobile import MobileController

                    await MobileController.execute(
                        action="press_key",
                        keycode=4,
                        device_id=params.get("device_id"),
                        disable_atlas=True,
                        disable_trace_screenshot=True,
                        expected_pkg=active_bundle_id
                    )
                    await asyncio.sleep(0.8)

                except Exception as e:
                    logger.exception(f"[{thread_id}] Error processing item {i}: {e}")
                    item["status"] = "failed"
                    item["error"] = str(e)
                    fail_count += 1

                if i % 5 == 0:
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)

            state["phase"] = "completed"
            state["updated_at"] = datetime.now().isoformat()
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            result_msg = f"Detail phase complete: {success_count} succeeded, {fail_count} failed"
            logger.info(f"[{thread_id}] {result_msg}")
            await activity_monitor.log_event("macro_thought", {"text": f"{result_msg}"}, thread_id)

            extracted_data["collect_results"] = {
                "total": len(state["items"]),
                "success": success_count,
                "failed": fail_count,
                "state_file": state_file
            }
            return True, result_msg, {"state_file": state_file}

        return True, "Collect loop processed", None

    @staticmethod
    def _extract_collect_items_from_xml(xml_content, anchor_rule, feature_config):
        import xml.etree.ElementTree as ET

        def _parse_bounds_local(bounds_str):
            bounds = parse_bounds(bounds_str)
            if bounds:
                return {"left": bounds[0], "top": bounds[1], "right": bounds[2], "bottom": bounds[3]}
            return None

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        items = []

        try:
            anchor_pattern = anchor_rule.get("pattern", "")
            offset_y = feature_config.get("offset_y", -200)
            feature_height = feature_config.get("height", 200)
            max_features = feature_config.get("max_features", 4)

            node_name = anchor_rule.get("node_name", "node")

            for node in root.iter(node_name):
                bounds_str = node.get("bounds", "")
                bounds = _parse_bounds_local(bounds_str)
                if not bounds:
                    continue

                text = node.get("text", "") or node.get("content-desc", "")
                if not text:
                    continue

                import re as re_mod

                if re_mod.search(anchor_pattern, text):
                    anchor_center_y = (bounds["top"] + bounds["bottom"]) / 2
                    signature = re_mod.sub(r'\s+', '', text)[:100]

                    feature_bounds = {
                        "top": anchor_center_y + offset_y,
                        "bottom": anchor_center_y + offset_y + feature_height
                    }

                    tap_y = anchor_center_y

                    item = {
                        "text": text,
                        "bounds": bounds_str,
                        "anchor_y": anchor_center_y,
                        "tap_x": (bounds["left"] + bounds["right"]) / 2,
                        "tap_y": tap_y,
                        "signature": signature,
                        "features": [],
                        "content_desc": node.get("content-desc", "")
                    }

                    feature_count = 0
                    for sibling in root.iter(node_name):
                        if feature_count >= max_features:
                            break
                        s_bounds_str = sibling.get("bounds", "")
                        s_bounds = _parse_bounds_local(s_bounds_str)
                        if not s_bounds:
                            continue
                        if s_bounds["top"] >= feature_bounds["top"] and s_bounds["bottom"] <= feature_bounds["bottom"]:
                            s_text = sibling.get("text", "") or sibling.get("content-desc", "")
                            if s_text:
                                item["features"].append(s_text)
                                feature_count += 1

                    items.append(item)

        except Exception as e:
            logger.warning(f"Error parsing XML for collect items: {e}", exc_info=True)

        return items
