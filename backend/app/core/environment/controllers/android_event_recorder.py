"""
Android Event Recorder - Records touch/input events from Android devices via ADB.
"""

import asyncio
import fcntl
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class AndroidEvent:
    """Represents a single Android input event."""
    timestamp: float
    event_type: str  # "touch_down", "touch_up", "touch_move", "key"
    x: int | None = None
    y: int | None = None
    key_code: int | None = None
    device_id: str = ""
    app_package: str | None = None


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

        # [FIX] Timestamp synchronization: kernel time to relative time
        self._start_time: float = 0.0          # System time when start_recording called
        self._kernel_time_base: float | None = None  # First kernel timestamp from getevent -t
        self._relative_offset_ms: float = 0.0  # MS offset from start_time when first event arrived

    def _find_input_device(self, device_id: str) -> str | None:
        """Find the touchscreen input device."""
        try:
            cmd = [self.adb_path, "-s", device_id, "shell", "getevent", "-lp"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                logger.warning(f"Failed to list input devices: {result.stderr}")
                return None

            # Look for touchscreen device
            lines = result.stdout.split("\n")
            current_device = None

            for line in lines:
                if line.startswith("add device"):
                    current_device = line.split(":")[-1].strip()
                elif "ABS_MT_POSITION_X" in line or "touchscreen" in line.lower():
                    if current_device:
                        logger.info(f"Found touchscreen device: {current_device}")
                        return current_device

            # Fallback to event2 (common for touch)
            return "/dev/input/event2"

        except Exception as e:
            logger.error(f"Error finding input device: {e}")
            return "/dev/input/event2"

    def _parse_event_line(self, line: str) -> tuple[AndroidEvent | None, float]:
        """
        Parse a getevent output line.

        Format can be:
        # 1. /dev/input/event2: 0003 0035 00000123
        # 2. 0003 0035 00000123 (when device is specified)
        # 3. [ 1234.567] /dev/input/event2: 0003 0035 00000123
        # 4. [ 1234.567] 0003 0035 00000123

        Returns:
            tuple: (AndroidEvent or None, relative_timestamp_ms or 0)
        """
        try:
            clean_line = line.strip()
            if not clean_line:
                return None, 0

            # [FIX] Extract kernel timestamp from getevent -t output
            # Format: [ 2003248.185078] /dev/input/event2: 0003 0035 00000286
            # Note: Huawei and some devices have leading spaces
            kernel_timestamp = None
            if "[" in clean_line and "]" in clean_line:
                ts_part = clean_line.split("]", 1)[0]
                if "[" in ts_part:
                    ts_str = ts_part.split("[", 1)[1].strip()
                    try:
                        kernel_timestamp = float(ts_str)
                        # Remove the timestamp part from clean_line
                        clean_line = clean_line.split("]", 1)[1].strip()
                    except ValueError:
                        pass

            # Handle device prefix if present: /dev/input/event2: 0003...
            if ":" in clean_line:
                parts = clean_line.split(":", 1)
                data_str = parts[1].strip()
            else:
                data_str = clean_line

            data = data_str.split()
            if len(data) < 3:
                return None, 0

            # Some lines might be labels if -l was used, we try to parse as hex
            try:
                ev_type = int(data[0], 16)
                ev_code = int(data[1], 16)
                ev_value = int(data[2], 16)
            except ValueError:
                # If they are labels (like EV_ABS), we skip for now
                return None, 0

            # [FIX] Calculate relative timestamp from kernel time
            relative_ts_ms = 0.0
            if kernel_timestamp is not None:
                if self._kernel_time_base is None:
                    # [NEW] Establish baseline on first event arrival
                    self._kernel_time_base = kernel_timestamp
                    # How much time passed since start_recording()?
                    self._relative_offset_ms = (time.time() - self._start_time) * 1000.0
                    relative_ts_ms = self._relative_offset_ms
                    logger.info(f"[AndroidEventRecorder] Baseline established: kernel={kernel_timestamp}, offset={self._relative_offset_ms:.2f}ms")
                else:
                    # Calculate offset from pre-set base
                    elapsed_kernel_ms = (kernel_timestamp - self._kernel_time_base) * 1000.0
                    relative_ts_ms = elapsed_kernel_ms + self._relative_offset_ms
            else:
                # Fallback if no kernel timestamp (unlikely with -t)
                relative_ts_ms = (time.time() - self._start_time) * 1000.0

            # EV_ABS (0x03) - Absolute events (touch)
            if ev_type == 0x03:
                # ABS_MT_POSITION_X (0x35)
                if ev_code == 0x35:
                    return AndroidEvent(
                        timestamp=relative_ts_ms,  # [FIX] Now stored as milliseconds
                        event_type="touch_x",
                        x=ev_value,
                        device_id=self.device_id or ""
                    ), relative_ts_ms
                # ABS_MT_POSITION_Y (0x36)
                elif ev_code == 0x36:
                    return AndroidEvent(
                        timestamp=relative_ts_ms,  # [FIX] Store as milliseconds
                        event_type="touch_y",
                        y=ev_value,
                        device_id=self.device_id or ""
                    ), relative_ts_ms
                # ABS_MT_TRACKING_ID (0x39) - touch down/up
                elif ev_code == 0x39:
                    # 0xffffffff is used for touch up
                    if ev_value == 0xffffffff or ev_value == 0xffffffff + 1 or ev_value == -1:
                        return AndroidEvent(
                            timestamp=relative_ts_ms,  # [FIX] Store as milliseconds
                            event_type="touch_up",
                            device_id=self.device_id or ""
                        ), relative_ts_ms
                    else:
                        return AndroidEvent(
                            timestamp=relative_ts_ms,  # [FIX] Store as milliseconds
                            event_type="touch_down",
                            device_id=self.device_id or ""
                        ), relative_ts_ms

            # EV_KEY (0x01) - Button events
            elif ev_type == 0x01:
                # BTN_TOUCH (0x14a) or generic key
                if ev_code == 0x14a:
                    # BTN_TOUCH is a reliable indicator of physical touch state
                    event_type = "touch_down" if ev_value == 1 else "touch_up"
                    return AndroidEvent(
                        timestamp=relative_ts_ms,  # [FIX] Store as milliseconds
                        event_type=event_type,
                        device_id=self.device_id or ""
                    ), relative_ts_ms
                # Power/Home/Back keys can also be useful
                else:
                    return AndroidEvent(
                        timestamp=relative_ts_ms,  # [FIX] Store as milliseconds
                        event_type="key",
                        key_code=ev_code,
                        device_id=self.device_id or ""
                    ), relative_ts_ms

            return None, 0

        except Exception as e:
            logger.debug(f"Failed to parse event line: {line.strip()}, error: {e}")
            return None, 0

    def _record_loop(self):
        """Main recording loop running in separate thread."""
        if not self.device_id:
            logger.error("No device_id set for recording")
            return

        # Use global getevent - captures from ALL devices.
        # This is more robust than trying to find the specific touchscreen device.
        cmd = [
            self.adb_path, "-s", self.device_id,
            "shell", "getevent", "-t"
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0
            )

            proc = self.process
            logger.info(f"[AndroidEventRecorder] Started Android event recording (PID: {proc.pid})")

            current_touch = {"x": 0, "y": 0, "down": False}
            raw_line_count = 0
            buffer = ""
            first_event_logged = False

            # Diagnostic ranges
            min_x, max_x = float('inf'), -float('inf')
            min_y, max_y = float('inf'), -float('inf')

            # Helper to get current app package efficiently
            def poll_package():
                now = time.time()
                if now - self._last_package_poll > 2.0: # Poll every 2 seconds
                    package_found = None

                    # Strategy 1: dumpsys activity activities (Most accurate for recently resumed)
                    try:
                        cmd_pkg = [self.adb_path, "-s", self.device_id, "shell", "dumpsys", "activity", "activities"]
                        pkg_proc = subprocess.run(cmd_pkg, capture_output=True, text=True, timeout=2)
                        for line in pkg_proc.stdout.splitlines():
                            if ("mResumedActivity" in line or "topResumedActivity" in line) and "/" in line:
                                match = re.search(r'([\w\.]+)/([\w\.\$]+)', line)
                                if match:
                                    package_found = match.group(1)
                                    break
                    except Exception:
                        pass

                    # Strategy 2: dumpsys window windows (Fallback)
                    if not package_found:
                        try:
                            cmd_pkg = [self.adb_path, "-s", self.device_id, "shell", "dumpsys", "window", "windows"]
                            pkg_proc = subprocess.run(cmd_pkg, capture_output=True, text=True, timeout=2)
                            for line in pkg_proc.stdout.splitlines():
                                if ("mCurrentFocus" in line or "mFocusedApp" in line) and "/" in line:
                                    match = re.search(r'([\w\.]+)/([\w\.\$]+)', line)
                                    if match:
                                        package_found = match.group(1)
                                        break
                        except Exception:
                            pass

                    # Strategy 3: dumpsys activity top (Last resort)
                    if not package_found:
                        try:
                            cmd_pkg = [self.adb_path, "-s", self.device_id, "shell", "dumpsys", "activity", "top"]
                            pkg_proc = subprocess.run(cmd_pkg, capture_output=True, text=True, timeout=2)
                            for line in pkg_proc.stdout.splitlines():
                                if "ACTIVITY" in line and "/" in line:
                                    match = re.search(r'ACTIVITY\s+([\w\.]+)/([\w\.\$]+)', line)
                                    if match:
                                        package_found = match.group(1)
                                        break
                        except Exception:
                            pass

                    if package_found:
                        self.current_package = package_found
                        logger.debug(f"[AndroidEventRecorder] Current package: {package_found}")

                    self._last_package_poll = now

            # Set non-blocking to allow checking stop_event frequently
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

                    buffer += chunk.decode('utf-8', errors='ignore')
                    if "\n" in buffer:
                        lines = buffer.split("\n")
                        buffer = lines.pop()

                        for line in lines:
                            raw_line_count += 1

                            event, relative_ts_ms = self._parse_event_line(line)
                            if not event:
                                continue

                            logger.debug(f"[AndroidEventRecorder] Captured: {event.event_type} (x={event.x}, y={event.y}) from line: {line!r}")

                            # [FIX] Log first valid event timestamp
                            if not first_event_logged and event.event_type in ("touch_x", "touch_y", "touch_down", "touch_up", "key"):
                                logger.info(f"[AndroidEventRecorder] First event: {event.event_type} at relative_ts={relative_ts_ms:.3f}ms")
                                first_event_logged = True

                            # Track touch state
                            if event.event_type == "touch_x":
                                current_touch["x"] = event.x or 0
                                if event.x is not None:
                                    min_x = min(min_x, event.x)
                                    max_x = max(max_x, event.x)
                            elif event.event_type == "touch_y":
                                current_touch["y"] = event.y or 0
                                if event.y is not None:
                                    min_y = min(min_y, event.y)
                                    max_y = max(max_y, event.y)

                            elif event.event_type == "touch_down":
                                if not current_touch["down"]:
                                    current_touch["down"] = True
                                    poll_package()
                                    # [FIX] Use the relative timestamp from kernel time
                                    data = AndroidEvent(
                                        timestamp=int(relative_ts_ms),  # [FIX] Store as integer milliseconds
                                        event_type="touch_down",
                                        x=current_touch["x"],
                                        y=current_touch["y"],
                                        device_id=self.device_id or "",
                                        app_package=self.current_package
                                    )
                                    self.events.append(data)
                                    if self.on_event_callback:
                                        self.on_event_callback(data)
                            elif event.event_type == "touch_up":
                                if current_touch["down"]:
                                    current_touch["down"] = False
                                    # [FIX] Use the relative timestamp from kernel time
                                    data = AndroidEvent(
                                        timestamp=int(relative_ts_ms),  # [FIX] Store as integer milliseconds
                                        event_type="touch_up",
                                        x=current_touch["x"],
                                        y=current_touch["y"],
                                        device_id=self.device_id or "",
                                        app_package=self.current_package
                                    )
                                    self.events.append(data)
                                    if self.on_event_callback:
                                        self.on_event_callback(data)
                            elif event.event_type == "key":
                                # [FIX] Use the relative timestamp from kernel time
                                data = AndroidEvent(
                                    timestamp=int(relative_ts_ms),  # [FIX] Store as integer milliseconds
                                    event_type="key",
                                    key_code=event.key_code, # Use the key_code from the parsed event
                                    device_id=self.device_id or "",
                                    app_package=self.current_package
                                )
                                self.events.append(data)
                                if self.on_event_callback:
                                    self.on_event_callback(data)
                            else: # For any other parsed AndroidEvent that doesn't have specific handling
                                # [FIX] Use the relative timestamp from kernel time
                                data = AndroidEvent(
                                    timestamp=int(relative_ts_ms),  # [FIX] Store as integer milliseconds
                                    event_type=event.event_type,
                                    x=event.x,
                                    y=event.y,
                                    key_code=event.key_code,
                                    device_id=self.device_id or "",
                                    app_package=self.current_package
                                )
                                self.events.append(data)
                                if self.on_event_callback:
                                    self.on_event_callback(data)

                        # DEBUG: Log counts to a fixed file
                        try:
                            with open("/tmp/debug_recorder_counts.log", "w") as f:
                                f.write(f"Raw lines: {raw_line_count}\nEvents: {len(self.events)}\n")
                                f.write(f"X range: {min_x} - {max_x}\nY range: {min_y} - {max_y}\n")
                        except:
                            pass

                except (BlockingIOError, InterruptedError):
                    time.sleep(0.01)
                    continue
                except Exception as e:
                    logger.debug(f"Error reading from adb: {e}")
                    break
            
            logger.debug(f"Exited recording loop after {raw_line_count} raw lines. Process poll: {proc.poll()}")

        except Exception as e:
            logger.error(f"Event recording error: {e}")
        finally:
            self.is_recording = False
            logger.info(f"Android event recording stopped. Captured {len(self.events)} events")


    def start_recording(self, device_id: str, callback=None) -> bool:
        """Start recording events from device."""
        if self.is_recording:
            logger.warning("Already recording")
            return False

        self.device_id = device_id
        self.events = []
        self.is_recording = True
        self.on_event_callback = callback
        self._stop_event.clear()

        self._stop_event.clear()

        # [CRITICAL] Record start time for relative offset calculation
        self._start_time = time.time()
        self._kernel_time_base = None
        self._relative_offset_ms = 0.0
        logger.info(f"[AndroidEventRecorder] Recording started at {self._start_time}")

        self._recording_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._recording_thread.start()

        return True

    def stop_recording(self) -> list[AndroidEvent]:
        """Stop recording and return captured events."""
        self._stop_event.set()
        self.is_recording = False

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                if self.process:
                    self.process.kill()
            self.process = None

        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=3)

        return self.events

    def to_trace_events(self, session_id: str, thread_id: str) -> list[dict]:
        """
        Convert Android events to trace event format for backend storage.

        [FIX] timestamp is now relative time in seconds (from recording start),
        not Unix epoch time. This aligns with video timing for keyframe extraction.
        """
        trace_events = []

        for event in self.events:
            # [FIX] event.timestamp is already in milliseconds
            relative_ms = int(event.timestamp)

            trace_events.append({
                "timestamp": relative_ms,  # Relative milliseconds from recording start
                "event_type": event.event_type,
                "target_selector": f"android://screen/{event.x}/{event.y}" if event.x is not None else None,
                "target_text": None,
                "payload": {
                    "x": event.x,
                    "y": event.y,
                    "device_id": event.device_id,
                    "platform": "android",
                    "package_name": event.app_package,
                    "relative_timestamp_ms": relative_ms,  # [NEW] Explicit field for clarity
                }
            })

        return trace_events
