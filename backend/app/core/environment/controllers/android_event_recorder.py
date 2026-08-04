"""
Android Event Recorder - Records touch/input events from Android devices via ADB.
"""

import asyncio
import fcntl
import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable

from app.core.environment.schemas import AndroidEvent, AndroidTraceEvent, DebounceConfig

logger = logging.getLogger(__name__)


class AndroidEventRecorder:
    """
    Records input events from Android device using adb shell getevent.
    """

    def __init__(self, adb_path: str = "adb"):
        self.adb_path = adb_path
        self.device_id: str | None = None
        self.process: subprocess.Popen | None = None
        self.is_recording = False
        self.events: list[AndroidEvent] = []
        self._recording_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.on_event_callback: Callable | None = None
        self.current_package: str | None = None
        self._last_package_poll: float = 0

        # Timestamp synchronization: kernel time to relative time
        self._start_time: float = 0.0          # System time when start_recording called
        self._kernel_time_base: float | None = None  # First kernel timestamp from getevent -t
        self._relative_offset_ms: float = 0.0  # MS offset from start_time when first event arrived

        # Video synchronization for keyframe extraction
        self._video_start_time: float | None = None  # Unix timestamp when video recording started
        self._time_offset_ms: float = 0.0      # Offset to add to event timestamps to sync with video

        self._debounce_config = DebounceConfig()
        self._last_event_time_ms: float = 0.0
        self._last_x: int = 0
        self._last_y: int = 0
        self._swipe_buffer: list[dict] = []  # Buffer for swipe aggregation
        self._swipe_start_time_ms: float = 0.0
        self._swipe_start_x: int = 0
        self._swipe_start_y: int = 0

    def _should_debounce(self, x: int, y: int, timestamp_ms: float) -> bool:
        """
        Check if event should be debounced (ignored).
        """
        time_delta = timestamp_ms - self._last_event_time_ms
        if time_delta < self._debounce_config.time_threshold_ms:
            # Within time window, check spatial threshold
            distance = ((x - self._last_x) ** 2 + (y - self._last_y) ** 2) ** 0.5
            if distance < self._debounce_config.spatial_threshold_px:
                return True
        return False

    def _emit_swipe_event(self, final_x: int, final_y: int, final_time_ms: float):
        """
        Emit a swipe event from the buffered points.
        """
        if not self._swipe_buffer:
            return

        duration_ms = final_time_ms - self._swipe_start_time_ms

        # Create swipe event
        swipe_event = AndroidEvent(
            timestamp=int(self._swipe_start_time_ms),
            event_type="swipe",
            x=self._swipe_start_x,
            y=self._swipe_start_y,
            device_id=self.device_id or "",
            app_package=self.current_package,
            swipe_end_x=final_x,
            swipe_end_y=final_y,
            swipe_duration_ms=duration_ms,
        )

        self.events.append(swipe_event)
        if self.on_event_callback:
            self.on_event_callback(swipe_event)

        logger.debug(f"Swipe emitted: ({self._swipe_start_x},{self._swipe_start_y}) -> ({final_x},{final_y}), duration={duration_ms:.1f}ms")

        # Clear buffer
        self._swipe_buffer = []

    def _start_swipe(self, x: int, y: int, timestamp_ms: float):
        """Start tracking a new swipe sequence."""
        self._swipe_start_x = x
        self._swipe_start_y = y
        self._swipe_start_time_ms = timestamp_ms
        self._swipe_buffer = [{"x": x, "y": y, "t": timestamp_ms}]

    def _add_swipe_point(self, x: int, y: int, timestamp_ms: float):
        """Add a point to current swipe buffer."""
        self._swipe_buffer.append({"x": x, "y": y, "t": timestamp_ms})

        # Maintain max points limit
        if len(self._swipe_buffer) > self._debounce_config.max_swipe_points:
            first = self._swipe_buffer[0]
            last = self._swipe_buffer[-1]
            step = len(self._swipe_buffer) // (self._debounce_config.max_swipe_points - 1)
            middle = [self._swipe_buffer[i * step] for i in range(1, self._debounce_config.max_swipe_points - 1)]
            self._swipe_buffer = [first] + middle + [last]

    def _parse_event_line(self, line: str) -> tuple[AndroidEvent | None, float]:
        """Parse a getevent output line."""
        try:
            clean_line = line.strip()
            if not clean_line:
                return None, 0

            kernel_timestamp = None
            if "[" in clean_line and "]" in clean_line:
                ts_part = clean_line.split("]", 1)[0]
                if "[" in ts_part:
                    ts_str = ts_part.split("[", 1)[1].strip()
                    try:
                        kernel_timestamp = float(ts_str)
                        clean_line = clean_line.split("]", 1)[1].strip()
                    except ValueError:
                        pass

            if ":" in clean_line:
                data_str = clean_line.split(":", 1)[1].strip()
            else:
                data_str = clean_line

            data = data_str.split()
            if len(data) < 3:
                return None, 0

            try:
                ev_type = int(data[0], 16)
                ev_code = int(data[1], 16)
                ev_value = int(data[2], 16)
            except ValueError:
                return None, 0

            relative_ts_ms = 0.0
            if kernel_timestamp is not None:
                if self._kernel_time_base is None:
                    # Fallback if _calibrate_clocks hasn't finished yet or failed
                    self._kernel_time_base = kernel_timestamp
                    self._relative_offset_ms = (time.time() - self._start_time) * 1000.0
                    relative_ts_ms = self._relative_offset_ms
                    logger.debug(f"[AndroidEventRecorder] Lazy calibration on first event: offset={self._relative_offset_ms:.1f}ms")
                else:
                    # Use calibrated base
                    elapsed_kernel_ms = (kernel_timestamp - self._kernel_time_base) * 1000.0
                    relative_ts_ms = elapsed_kernel_ms + self._relative_offset_ms
            else:
                # No kernel timestamp (unlikely with -t), use host time
                relative_ts_ms = (time.time() - self._start_time) * 1000.0

            if ev_type == 0x03:
                if ev_code == 0x35:
                    return AndroidEvent(timestamp=relative_ts_ms, event_type="touch_x", x=ev_value, device_id=self.device_id or ""), relative_ts_ms
                elif ev_code == 0x36:
                    return AndroidEvent(timestamp=relative_ts_ms, event_type="touch_y", y=ev_value, device_id=self.device_id or ""), relative_ts_ms
                elif ev_code == 0x39:
                    if ev_value in (0xFFFFFFFF, -1):
                        return AndroidEvent(timestamp=relative_ts_ms, event_type="touch_up", device_id=self.device_id or ""), relative_ts_ms
                    else:
                        return AndroidEvent(timestamp=relative_ts_ms, event_type="touch_down", device_id=self.device_id or ""), relative_ts_ms

            elif ev_type == 0x01:
                if ev_code == 0x14A:
                    event_type = "touch_down" if ev_value == 1 else "touch_up"
                    return AndroidEvent(timestamp=relative_ts_ms, event_type=event_type, device_id=self.device_id or ""), relative_ts_ms
                else:
                    return AndroidEvent(timestamp=relative_ts_ms, event_type="key", key_code=ev_code, device_id=self.device_id or ""), relative_ts_ms

            return None, 0

        except Exception as e:
            logger.debug(f"Failed to parse event line: {line.strip()}, error: {e}")
            return None, 0

    def get_current_package(self, device_id: str | None = None) -> str | None:
        """
        Get the current active app package on the device.
        Uses centralized adb_driver with caching.
        """
        from app.infrastructure.drivers.adb import adb_driver

        target_device = device_id or self.device_id
        if not target_device:
            return None

        try:
            app_info = adb_driver.get_current_app(device_id=target_device)
            pkg = app_info.get("package")
            if pkg and pkg not in ("error", "unknown"):
                self.current_package = pkg
                return pkg
        except Exception as e:
            logger.debug(f"[AndroidEventRecorder] Failed to get package: {e}")

        return self.current_package

    def _record_loop(self):
        """Main recording loop running in separate thread."""
        if not self.device_id:
            logger.error("No device_id set for recording")
            return

        cmd = [self.adb_path, "-s", self.device_id, "shell", "getevent", "-t"]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )
            proc = self.process
            logger.info(f"[AndroidEventRecorder] Started recording (PID: {proc.pid})")

            # Initial poll
            self.get_current_package()

            current_touch = {"x": 0, "y": 0, "down": False}
            buffer = ""

            fd = proc.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            while not self._stop_event.is_set():
                try:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        if proc.poll() is not None:
                            break
                        time.sleep(0.01)
                        continue

                    buffer += chunk.decode("utf-8", errors="ignore")
                    if "\n" in buffer:
                        lines = buffer.split("\n")
                        buffer = lines.pop()
                        for line in lines:
                            event, relative_ts_ms = self._parse_event_line(line)
                            if not event:
                                continue

                            if event.event_type == "touch_x":
                                current_touch["x"] = event.x or 0
                                if current_touch["down"] and self._swipe_buffer:
                                    if not self._should_debounce(current_touch["x"], current_touch["y"], relative_ts_ms):
                                        self._add_swipe_point(current_touch["x"], current_touch["y"], relative_ts_ms)
                                        self._last_x, self._last_y, self._last_event_time_ms = current_touch["x"], current_touch["y"], relative_ts_ms

                            elif event.event_type == "touch_y":
                                current_touch["y"] = event.y or 0

                            elif event.event_type == "touch_down":
                                if not current_touch["down"]:
                                    current_touch["down"] = True
                                    self.get_current_package()

                                    if self._swipe_buffer:
                                        self._emit_swipe_event(self._last_x, self._last_y, self._last_event_time_ms)

                                    self._start_swipe(current_touch["x"], current_touch["y"], relative_ts_ms)
                                    self._last_x, self._last_y, self._last_event_time_ms = current_touch["x"], current_touch["y"], relative_ts_ms

                                    data = AndroidEvent(
                                        timestamp=int(relative_ts_ms),
                                        event_type="touch_down",
                                        x=current_touch["x"],
                                        y=current_touch["y"],
                                        device_id=self.device_id or "",
                                        app_package=self.current_package,
                                    )
                                    self.events.append(data)
                                    if self.on_event_callback:
                                        self.on_event_callback(data)

                            elif event.event_type == "touch_up":
                                if current_touch["down"]:
                                    current_touch["down"] = False
                                    if self._swipe_buffer:
                                        self._emit_swipe_event(current_touch["x"], current_touch["y"], relative_ts_ms)

                                    data = AndroidEvent(
                                        timestamp=int(relative_ts_ms),
                                        event_type="touch_up",
                                        x=current_touch["x"],
                                        y=current_touch["y"],
                                        device_id=self.device_id or "",
                                        app_package=self.current_package,
                                    )
                                    self.events.append(data)
                                    if self.on_event_callback:
                                        self.on_event_callback(data)

                            elif event.event_type == "key":
                                data = AndroidEvent(
                                    timestamp=int(relative_ts_ms),
                                    event_type="key",
                                    key_code=event.key_code,
                                    device_id=self.device_id or "",
                                    app_package=self.current_package,
                                )
                                self.events.append(data)
                                if self.on_event_callback:
                                    self.on_event_callback(data)

                except (BlockingIOError, InterruptedError):
                    time.sleep(0.01)
                    continue
                except Exception as e:
                    logger.debug(f"Error reading from adb: {e}")
                    break

        except Exception as e:
            logger.error(f"Event recording error: {e}")
        finally:
            self.is_recording = False
            logger.info(f"Android event recording stopped. Captured {len(self.events)} events")

    async def _calibrate_clocks(self):
        """
        Synchronize Android kernel clock with host time immediately.
        Avoids the 0.5s-1.0s startup latency of the adb process.
        """
        from app.infrastructure.drivers.adb import adb_driver

        try:
            # 1. Fetch kernel uptime (seconds)
            kernel_uptime = adb_driver.get_uptime(self.device_id)
            # 2. Record host time (Unix timestamp)
            host_now = time.time()

            if kernel_uptime > 0:
                self._kernel_time_base = kernel_uptime
                # Host time at the moment kernel_uptime was 0 (theoretically)
                self._host_at_kernel_zero = host_now - kernel_uptime
                # Calculate the relative start time offset
                # (How many MS into the video/host-recording-session was the kernel_uptime captured)
                self._relative_offset_ms = (host_now - self._start_time) * 1000.0

                logger.info(
                    f"[AndroidEventRecorder] Clock calibrated: "
                    f"Kernel={kernel_uptime:.3f}s, Host={host_now:.3f}s. "
                    f"Offset={self._relative_offset_ms:.1f}ms"
                )
        except Exception as e:
            logger.warning(f"[AndroidEventRecorder] Failed to calibrate clocks: {e}")

    def start_recording(self, device_id: str, callback=None, video_start_time: float | None = None) -> bool:
        """Start recording events."""
        if self.is_recording:
            return False
        self.device_id = device_id
        self.events = []
        self.is_recording = True
        self.on_event_callback = callback
        self._stop_event.clear()
        self._start_time = time.time()
        self._kernel_time_base = None
        self._video_start_time = video_start_time
        if video_start_time and video_start_time > 0:
            self._time_offset_ms = (self._start_time - video_start_time) * 1000.0
        else:
            self._time_offset_ms = 0.0

        # Sync clock immediately to avoid ADB process startup lag
        # We use a helper task for this since start_recording is often called from sync code
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._calibrate_clocks())
            else:
                asyncio.run(self._calibrate_clocks())
        except Exception:
            # Fallback if loop is unavailable
            pass

        self._recording_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._recording_thread.start()
        return True

    def set_video_start_time(self, video_start_time: float):
        """
        Update the video start time dynamically.
        Useful when the exact recording start time is detected later (e.g., from scrcpy logs).
        """
        self._video_start_time = video_start_time
        if video_start_time and video_start_time > 0:
            # Re-calculate offset: (Recorder Start - Video Start)
            self._time_offset_ms = (self._start_time - video_start_time) * 1000.0
            logger.info(f"[AndroidEventRecorder] Updated video_start_time: {video_start_time}, new offset: {self._time_offset_ms:.1f}ms")

    def stop_recording(self) -> list[AndroidEvent]:
        """Stop recording."""
        self._stop_event.set()
        self.is_recording = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except (OSError, ProcessLookupError):
                if self.process:
                    self.process.kill()
            self.process = None
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=3)
        return self.events

    def to_trace_events(self, session_id: str, thread_id: str) -> list[AndroidTraceEvent]:
        """Convert to trace events."""
        trace_events: list[AndroidTraceEvent] = []
        for event in self.events:
            relative_ms = int(event.timestamp + self._time_offset_ms)
            if event.event_type == "swipe":
                payload = {
                    "x": event.x, "y": event.y,
                    "end_x": event.swipe_end_x, "end_y": event.swipe_end_y,
                    "duration_ms": event.swipe_duration_ms,
                    "device_id": event.device_id,
                    "platform": "android",
                    "package_name": event.app_package,
                    "relative_timestamp_ms": relative_ms,
                    "is_swipe": True,
                }
                target_x, target_y = (event.swipe_end_x or event.x), (event.swipe_end_y or event.y)
            else:
                payload = {
                    "x": event.x, "y": event.y, "key_code": event.key_code,
                    "device_id": event.device_id, "platform": "android",
                    "package_name": event.app_package,
                    "relative_timestamp_ms": relative_ms,
                }
                target_x, target_y = event.x, event.y

            trace_events.append(
                AndroidTraceEvent(
                    timestamp=relative_ms,
                    event_type=event.event_type,
                    target_selector=f"android://screen/{target_x}/{target_y}"
                    if target_x is not None
                    else None,
                    target_text=None,
                    payload=payload,
                )
            )
        return trace_events
