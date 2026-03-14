"""
VerificationWorker - Real Environment Step Executor

Executes macro steps in the actual target environment (browser, mobile, desktop).
Interfaces with existing controllers to perform actions and capture state.
"""

import logging
import time
from typing import Any, Dict, Optional

from app.core.execution.macro.verification_models import AgentConfig, EnvironmentConfig

logger = logging.getLogger(__name__)


class VerificationWorker:
    """
    Worker that executes verification steps in real environment.

    Responsibilities:
    1. Initialize connection to target environment
    2. Execute individual macro steps
    3. Capture UI state (screenshots, element dumps)
    4. Provide unified interface regardless of platform
    """

    def __init__(
        self,
        environment_config: EnvironmentConfig,
        agent_config: AgentConfig
    ):
        self.config = environment_config
        self.agent_config = agent_config

        # Platform-specific controllers (initialized lazily)
        self._browser_controller: Optional[Any] = None
        self._mobile_controller: Optional[Any] = None
        self._desktop_controller: Optional[Any] = None

        # Current state
        self._current_platform: Optional[str] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize connection to target environment"""
        platform = self.config.platform

        if platform == "web":
            await self._init_browser()
        elif platform == "android":
            await self._init_mobile()
        elif platform == "desktop":
            await self._init_desktop()
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        self._current_platform = platform
        self._initialized = True
        logger.info(f"[Worker] Initialized for platform: {platform}")

    async def _init_browser(self) -> None:
        """Initialize browser controller"""
        try:
            from app.infrastructure.automation.web.controller import BrowserController

            self._browser_controller = BrowserController()

            # Apply browser config if provided
            if self.config.browser_config:
                await self._browser_controller.configure(self.config.browser_config)

        except ImportError as e:
            logger.error(f"[Worker] Failed to import BrowserController: {e}")
            raise RuntimeError("Browser automation not available") from e

    async def _init_mobile(self) -> None:
        """Initialize mobile controller"""
        try:
            from app.core.environment.controllers.mobile_controller import MobileController

            self._mobile_controller = MobileController()
            # MobileController uses classmethods, no connect needed

        except ImportError as e:
            logger.error(f"[Worker] Failed to import MobileController: {e}")
            raise RuntimeError("Mobile automation not available") from e

    async def _init_desktop(self) -> None:
        """Initialize desktop controller"""
        try:
            from app.infrastructure.automation.desktop.controller import DesktopController

            self._desktop_controller = DesktopController()

        except ImportError as e:
            logger.error(f"[Worker] Failed to import DesktopController: {e}")
            raise RuntimeError("Desktop automation not available") from e

    async def execute_step(
        self,
        step: Dict[str, Any],
        step_validator: Optional[Any] = None
    ) -> Any:
        """
        Execute a single macro step

        Args:
            step: Macro step dictionary with type, event_type, payload, etc.
            step_validator: Optional validator callback for sub-step validation (for loop steps)

        Returns:
            Execution result (varies by action type)
        """
        if not self._initialized:
            raise RuntimeError("Worker not initialized")

        step_type = step.get("type", "action")
        event_type = step.get("event_type", "")
        source = step.get("source", "dom")
        payload = step.get("payload", {})

        logger.debug(f"[Worker] Executing step: {event_type} ({source}, type={step_type})")

        try:
            # Handle loop type - execute all sub-steps
            if step_type == "loop":
                return await self._execute_loop_step(step, step_validator=step_validator)

            # Handle extract type
            if step_type == "extract":
                return await self._execute_extract_step(step)

            # Route to appropriate executor based on source/platform
            if source == "dom" or self._current_platform == "web":
                return await self._execute_browser_step(step_type, event_type, payload)
            elif source == "mobile" or self._current_platform == "android":
                return await self._execute_mobile_step(step_type, event_type, payload)
            elif source == "desktop" or self._current_platform == "desktop":
                return await self._execute_desktop_step(step_type, event_type, payload)
            else:
                raise ValueError(f"Unknown source/platform: {source}/{self._current_platform}")

        except Exception as e:
            logger.error(f"[Worker] Step execution failed: {e}")
            return {"error": "execution_failed", "message": str(e), "step": step}

    async def _execute_browser_step(
        self,
        step_type: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Any:
        """Execute browser/DOM step"""
        if not self._browser_controller:
            raise RuntimeError("Browser controller not available")

        controller = self._browser_controller

        # Navigation
        if event_type in ("goto", "navigate"):
            url = payload.get("url") or payload.get("value")
            return await controller.goto(url)

        # Click
        elif event_type == "click":
            selector = payload.get("selector")
            x = payload.get("x")
            y = payload.get("y")

            if selector:
                return await controller.click(selector)
            elif x is not None and y is not None:
                return await controller.click_at(x, y)
            else:
                raise ValueError("Click requires selector or coordinates")

        # Input/Type
        elif event_type in ("input", "type_text"):
            selector = payload.get("selector")
            text = payload.get("text") or payload.get("value", "")
            clear = payload.get("clear", True)

            if selector:
                if clear:
                    await controller.clear(selector)
                return await controller.type_text(selector, text)
            else:
                raise ValueError("Input requires selector")

        # Key press
        elif event_type == "key_press":
            key = payload.get("key")
            return await controller.key_press(key)

        # Scroll
        elif event_type == "scroll":
            direction = payload.get("direction", "down")
            amount = payload.get("amount", 500)
            return await controller.scroll(direction, amount)

        # Wait (支持 duration_ms 和 seconds)
        elif event_type in ("wait", "wait_for"):
            duration_ms = payload.get("duration_ms")
            seconds = payload.get("seconds")
            if duration_ms is not None:
                duration = duration_ms
            elif seconds is not None:
                duration = seconds * 1000
            else:
                duration = 1000  # 默认 1 秒
            condition = payload.get("condition")

            if condition:
                return await controller.wait_for(condition, timeout=duration / 1000)
            else:
                import asyncio
                await asyncio.sleep(duration / 1000)
                return {"status": "waited", "duration_ms": int(duration)}

        # Extract/Get text
        elif event_type in ("get_text", "extract"):
            selector = payload.get("selector")
            if selector:
                return await controller.get_text(selector)
            return {"text": ""}

        # Get HTML
        elif event_type == "get_html":
            selector = payload.get("selector")
            return await controller.get_html(selector)

        # Get attribute
        elif event_type == "get_attribute":
            selector = payload.get("selector")
            attribute = payload.get("attribute", "value")
            return await controller.get_attribute(selector, attribute)

        # Run JavaScript
        elif event_type in ("run_js", "evaluate"):
            script = payload.get("script") or payload.get("code", "")
            return await controller.evaluate(script)

        # Screenshot
        elif event_type == "screenshot":
            return await controller.screenshot()

        # Dump UI
        elif event_type == "dump_ui":
            return await controller.dump_tree()

        else:
            logger.warning(f"[Worker] Unknown browser event type: {event_type}")
            return {"status": "skipped", "reason": f"Unknown event type: {event_type}"}

    async def _execute_mobile_step(
        self,
        step_type: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Any:
        """Execute mobile/Android step using MobileController.execute"""
        import asyncio
        from app.core.environment.controllers.mobile_controller import MobileController
        from app.infrastructure.drivers.adb import adb_driver

        # Map event types to MobileController actions
        action = event_type
        device_id = self.config.device_id

        # App launch
        if event_type == "open_app":
            package = payload.get("package") or payload.get("package_name")
            force_stop = payload.get("force_stop", False)
            return await MobileController.execute(
                action='open_app',
                text=package,
                device_id=device_id,
                force_stop=force_stop,
                disable_trace_screenshot=True,
                disable_atlas=True
            )

        # Tap/Click
        elif event_type == "tap" or event_type == "click":
            x = payload.get("x")
            y = payload.get("y")
            selector = payload.get("selector")

            if x is not None and y is not None:
                # Convert relative to absolute coordinates if needed
                if x < 1 and y < 1:
                    # Get screen size using adb_driver directly
                    try:
                        screen = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                        if screen:
                            abs_x = int(x * screen[0])
                            abs_y = int(y * screen[1])
                        else:
                            abs_x, abs_y = int(x * 1080), int(y * 2340)
                    except Exception as e:
                        logger.warning(f"[Worker] Failed to get screen size: {e}, using defaults")
                        abs_x, abs_y = int(x * 1080), int(y * 2340)
                else:
                    abs_x, abs_y = int(x), int(y)

                return await MobileController.execute(
                    action='click',
                    x=abs_x,
                    y=abs_y,
                    device_id=device_id,
                    disable_trace_screenshot=True,
                    disable_atlas=True
                )
            elif selector:
                return await MobileController.execute(
                    action='click',
                    element_name=selector,
                    device_id=device_id,
                    disable_trace_screenshot=True,
                    disable_atlas=True
                )
            else:
                raise ValueError("Tap requires coordinates or selector")

        # Input text
        elif event_type == "input" or event_type == "input_text":
            text = payload.get("text") or payload.get("value", "")
            return await MobileController.execute(
                action='input_text',
                text=text,
                device_id=device_id,
                disable_trace_screenshot=True,
                disable_atlas=True
            )

        # Back button
        elif event_type == "back":
            return await MobileController.execute(
                action='press_key',
                keycode=4,
                device_id=device_id,
                disable_trace_screenshot=True,
                disable_atlas=True
            )

        # Home button
        elif event_type == "home":
            return await MobileController.execute(
                action='press_key',
                keycode=3,
                device_id=device_id,
                disable_trace_screenshot=True,
                disable_atlas=True
            )

        # Wait (支持 duration_ms 和 seconds)
        elif event_type == "wait":
            duration_ms = payload.get("duration_ms")
            seconds = payload.get("seconds")
            if duration_ms is not None:
                duration = duration_ms
            elif seconds is not None:
                duration = seconds * 1000
            else:
                duration = 1000  # 默认 1 秒
            import asyncio
            await asyncio.sleep(duration / 1000)
            return {"status": "waited", "duration_ms": int(duration)}

        # Screenshot
        elif event_type == "screenshot":
            result = await MobileController.execute(
                action='screenshot',
                device_id=device_id,
                disable_trace_screenshot=True,
                disable_atlas=True
            )
            # Parse screenshot path from result
            if isinstance(result, str) and result.startswith("Screenshot: "):
                return {"status": "success", "screenshot_path": result.replace("Screenshot: ", "").strip()}
            return {"status": "success", "result": result}

        # Dump UI
        elif event_type == "dump_ui":
            return await MobileController.execute(
                action='dump_ui',
                device_id=device_id,
                disable_trace_screenshot=True,
                disable_atlas=True
            )

        # Scroll (swipe)
        elif event_type == "scroll":
            direction = payload.get("direction", "down")
            distance = payload.get("distance", 0.3)
            # Convert relative distance to pixels (approximate)
            try:
                screen = await asyncio.to_thread(adb_driver.get_screen_size, device_id=device_id)
                if screen:
                    height = screen[1]
                    swipe_distance = int(height * distance)
                    # Calculate start/end based on direction
                    center_x = int(screen[0] * 0.5)
                    center_y = int(screen[1] * 0.5)
                    if direction == "down":
                        start_y = center_y + swipe_distance // 2
                        end_y = center_y - swipe_distance // 2
                    else:  # up
                        start_y = center_y - swipe_distance // 2
                        end_y = center_y + swipe_distance // 2
                    return await MobileController.execute(
                        action='swipe',
                        x=center_x,
                        y=start_y,
                        x2=center_x,
                        y2=end_y,
                        device_id=device_id,
                        disable_trace_screenshot=True,
                        disable_atlas=True
                    )
            except Exception as e:
                logger.warning(f"[Worker] Scroll failed: {e}")
            return {"status": "skipped", "reason": "scroll not supported"}

        else:
            logger.warning(f"[Worker] Unknown mobile event type: {event_type}, step_type: {step_type}")
            return {"status": "skipped", "reason": f"Unknown event type: {event_type}"}

    async def _execute_desktop_step(
        self,
        step_type: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> Any:
        """Execute desktop step"""
        if not self._desktop_controller:
            raise RuntimeError("Desktop controller not available")

        controller = self._desktop_controller

        # Launch app
        if event_type == "launch_app":
            app_name = payload.get("package_name") or payload.get("app_name")
            return await controller.launch_app(app_name)

        # AppleScript
        elif event_type == "applescript":
            script = payload.get("script") or payload.get("code", "")
            return await controller.run_applescript(script)

        # Key press
        elif event_type == "key_press":
            key = payload.get("key")
            modifiers = payload.get("modifiers", [])
            return await controller.key_press(key, modifiers)

        # Click
        elif event_type == "click":
            x = payload.get("x")
            y = payload.get("y")
            return await controller.click(x, y)

        # Drag & Drop
        elif event_type == "drag_drop":
            x1 = payload.get("x1") or payload.get("start_x")
            y1 = payload.get("y1") or payload.get("start_y")
            x2 = payload.get("x2") or payload.get("end_x")
            y2 = payload.get("y2") or payload.get("end_y")
            return await controller.drag_drop(x1, y1, x2, y2)

        # Wait (支持 duration_ms 和 seconds)
        elif event_type == "wait":
            duration_ms = payload.get("duration_ms")
            seconds = payload.get("seconds")
            if duration_ms is not None:
                duration = duration_ms
            elif seconds is not None:
                duration = seconds * 1000
            else:
                duration = 1000  # 默认 1 秒
            import asyncio
            await asyncio.sleep(duration / 1000)
            return {"status": "waited", "duration_ms": int(duration)}

        # Screenshot
        elif event_type == "screenshot":
            return await self._desktop_controller.screenshot()

        else:
            logger.warning(f"[Worker] Unknown desktop event type: {event_type}")
            return {"status": "skipped", "reason": f"Unknown event type: {event_type}"}

    async def _execute_loop_step(
        self,
        step: Dict[str, Any],
        step_validator: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a loop step - iterates over sub-steps

        Args:
            step: Loop step dictionary with 'steps' array and optional 'condition', 'max_iterations'
            step_validator: Optional validator callback for sub-step validation (step, step_number) -> result

        Returns:
            Execution results for all iterations
        """
        import asyncio

        sub_steps = step.get("steps", [])
        max_iterations = step.get("max_iterations", 50)
        condition = step.get("condition", {})
        loop_results = []

        logger.info(f"[Worker] Executing loop with {len(sub_steps)} sub-steps, max {max_iterations} iterations")

        # For verification, we execute only 1 iteration (to save time)
        # In production, this would iterate until condition is met or max_iterations reached
        iterations = 1  # Limit to 1 iteration for verification

        for iteration in range(iterations):
            logger.info(f"[Worker] Loop iteration {iteration + 1}/{iterations}")
            iteration_results = []

            for sub_idx, sub_step in enumerate(sub_steps):
                # Use validator if provided (for anomaly detection and adaptation)
                if step_validator:
                    sub_step_num = step.get("step_number", 0) * 100 + sub_idx + 1
                    sub_result = await step_validator(sub_step, sub_step_num)
                    iteration_results.append({
                        "step": sub_step.get("step_number", sub_idx + 1),
                        "step_number": sub_step_num,
                        "result": sub_result,
                        "validated": True
                    })
                else:
                    # Direct execution without validation
                    sub_result = await self.execute_step(sub_step)
                    iteration_results.append({
                        "step": sub_step.get("step_number", sub_idx + 1),
                        "result": sub_result,
                        "validated": False
                    })
                # Small delay between sub-steps
                await asyncio.sleep(0.5)

            loop_results.append({
                "iteration": iteration + 1,
                "steps": iteration_results
            })

        logger.info(f"[Worker] Loop completed with {len(loop_results)} iteration(s)")
        return {
            "status": "completed",
            "iterations": len(loop_results),
            "results": loop_results,
            "validated": step_validator is not None
        }

    async def _execute_extract_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an extract step (GUI data extraction)

        Args:
            step: Extract step dictionary with 'key', 'extract_type', 'payload'

        Returns:
            Extraction result
        """
        from app.core.environment.controllers.mobile_controller import MobileController

        key = step.get("key", "unknown")
        extract_type = step.get("extract_type", "gui_extract")
        payload = step.get("payload", {})
        extraction_method = payload.get("extraction_method", "ocr_nearby")
        device_id = self.config.device_id

        logger.info(f"[Worker] Extracting data: key={key}, method={extraction_method}")

        # For verification, take a screenshot and return placeholder data
        try:
            result = await MobileController.execute(
                action='screenshot',
                device_id=device_id,
                disable_trace_screenshot=True,
                disable_atlas=True
            )
            # Parse screenshot path from result
            screenshot_path = None
            if isinstance(result, str) and result.startswith("Screenshot: "):
                screenshot_path = result.replace("Screenshot: ", "").strip()
            return {
                "status": "extracted",
                "key": key,
                "method": extraction_method,
                "screenshot": screenshot_path,
                "data": f"Extracted data for {key} using {extraction_method}"
            }
        except Exception as e:
            logger.warning(f"[Worker] Extract failed: {e}")
            return {"status": "skipped", "reason": f"extract failed: {e}"}

    async def capture_state(self) -> Dict[str, Any]:
        """
        Capture current UI state

        Returns:
            Dictionary with elements, screenshot, activity, etc.
        """
        state = {
            "platform": self._current_platform,
            "timestamp": time.time(),
            "elements": [],
            "screenshot": None,
            "current_activity": None,
        }

        try:
            if self._current_platform == "web" and self._browser_controller:
                # Get page info
                state["url"] = await self._browser_controller.get_url()
                state["title"] = await self._browser_controller.get_title()

                # Get element tree
                dump = await self._browser_controller.dump_tree()
                state["elements"] = dump.get("elements", [])

                # Screenshot if enabled
                if self.agent_config.enable_screenshot_analysis:
                    state["screenshot"] = await self._browser_controller.screenshot()

            elif self._current_platform == "android":
                from app.core.environment.controllers.mobile_controller import MobileController

                # Get current app/activity
                current_app = await MobileController.get_current_app_cached(self.config.device_id)
                state["current_activity"] = current_app.get("activity")
                state["package_name"] = current_app.get("package")

                # Get UI dump via execute
                ui_result = await MobileController.execute(
                    action='dump_ui',
                    device_id=self.config.device_id
                )
                if isinstance(ui_result, dict):
                    state["elements"] = ui_result.get("elements", [])

                # Screenshot if enabled
                if self.agent_config.enable_screenshot_analysis:
                    result = await MobileController.execute(
                        action='screenshot',
                        device_id=self.config.device_id
                    )
                    # Parse screenshot path from result message
                    if isinstance(result, str) and result.startswith("Screenshot: "):
                        screenshot_path = result.replace("Screenshot: ", "").strip()
                        state["screenshot"] = screenshot_path
                    elif isinstance(result, dict) and result.get("screenshot"):
                        state["screenshot"] = result["screenshot"]

            elif self._current_platform == "desktop" and self._desktop_controller:
                # Get active window info
                window_info = await self._desktop_controller.get_active_window()
                state["current_activity"] = window_info.get("app_name")
                state["window_title"] = window_info.get("title")

                # Screenshot if enabled
                if self.agent_config.enable_screenshot_analysis:
                    state["screenshot"] = await self._desktop_controller.screenshot()

        except Exception as e:
            logger.error(f"[Worker] Failed to capture state: {e}")
            state["error"] = str(e)

        return state

    async def cleanup(self) -> None:
        """Clean up resources"""
        logger.info("[Worker] Cleaning up resources")

        try:
            if self._browser_controller:
                await self._browser_controller.close()
                self._browser_controller = None

            # MobileController uses classmethods, no disconnect needed
            # Just clear the reference
            if self._mobile_controller:
                self._mobile_controller = None

            if self._desktop_controller:
                await self._desktop_controller.cleanup()
                self._desktop_controller = None

        except Exception as e:
            logger.error(f"[Worker] Cleanup error: {e}")

        self._initialized = False

