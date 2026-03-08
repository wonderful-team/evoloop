"""
Android Event Recorder - Records touch/input events from Android devices via ADB.
"""

import asyncio
import logging
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

    def _parse_event_line(self, line: str) -> AndroidEvent | None:
        """Parse a getevent output line."""
        # Format: /dev/input/event2: 0003 0035 00000123
        #         device      : type code   value
        try:
            if ":" not in line:
                return None

            parts = line.split(":")
            if len(parts) < 2:
                return None

            data = parts[1].strip().split()
            if len(data) < 3:
                return None

            ev_type = int(data[0], 16)
            ev_code = int(data[1], 16)
            ev_value = int(data[2], 16)

            # EV_ABS (0x03) - Absolute events (touch)
            if ev_type == 0x03:
                # ABS_MT_POSITION_X (0x35)
                if ev_code == 0x35:
                    return AndroidEvent(
                        timestamp=time.time(),
                        event_type="touch_x",
                        x=ev_value,
                        device_id=self.device_id or ""
                    )
                # ABS_MT_POSITION_Y (0x36)
                elif ev_code == 0x36:
                    return AndroidEvent(
                        timestamp=time.time(),
                        event_type="touch_y",
                        y=ev_value,
                        device_id=self.device_id or ""
                    )
                # ABS_MT_TRACKING_ID (0x39) - touch down/up
                elif ev_code == 0x39:
                    if ev_value == 0xffffffff or ev_value == -1:
                        return AndroidEvent(
                            timestamp=time.time(),
                            event_type="touch_up",
                            device_id=self.device_id or ""
                        )
                    else:
                        return AndroidEvent(
                            timestamp=time.time(),
                            event_type="touch_down",
                            device_id=self.device_id or ""
                        )

            return None

        except Exception as e:
            logger.debug(f"Failed to parse event line: {line}, error: {e}")
            return None

    def _record_loop(self):
        """Main recording loop running in separate thread."""
        if not self.device_id:
            logger.error("No device_id set for recording")
            return

        input_device = self._find_input_device(self.device_id)
        if not input_device:
            logger.error("Could not find touchscreen input device")
            return

        cmd = [
            self.adb_path, "-s", self.device_id,
            "shell", "getevent", "-tl", input_device
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            logger.info(f"Started Android event recording on {input_device}")

            current_touch = {"x": 0, "y": 0, "down": False}

            while not self._stop_event.is_set() and self.process.poll() is None:
                try:
                    line = self.process.stdout.readline()
                    if not line:
                        continue

                    event = self._parse_event_line(line)
                    if not event:
                        continue

                    # Track touch state
                    if event.event_type == "touch_x":
                        current_touch["x"] = event.x or 0
                    elif event.event_type == "touch_y":
                        current_touch["y"] = event.y or 0
                    elif event.event_type == "touch_down":
                        current_touch["down"] = True
                        # Record touch down with coordinates
                        self.events.append(AndroidEvent(
                            timestamp=time.time(),
                            event_type="touch_down",
                            x=current_touch["x"],
                            y=current_touch["y"],
                            device_id=self.device_id
                        ))
                    elif event.event_type == "touch_up":
                        current_touch["down"] = False
                        self.events.append(AndroidEvent(
                            timestamp=time.time(),
                            event_type="touch_up",
                            x=current_touch["x"],
                            y=current_touch["y"],
                            device_id=self.device_id
                        ))

                except Exception as e:
                    logger.debug(f"Error processing event line: {e}")

        except Exception as e:
            logger.error(f"Event recording error: {e}")
        finally:
            self.is_recording = False
            logger.info(f"Android event recording stopped. Captured {len(self.events)} events")

    def start_recording(self, device_id: str) -> bool:
        """Start recording events from device."""
        if self.is_recording:
            logger.warning("Already recording")
            return False

        self.device_id = device_id
        self.events = []
        self.is_recording = True
        self._stop_event.clear()

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
        """Convert Android events to trace event format for backend storage."""
        trace_events = []

        for event in self.events:
            trace_events.append({
                "timestamp": int(event.timestamp * 1000),  # Convert to milliseconds
                "event_type": event.event_type,
                "target_selector": f"android://screen/{event.x}/{event.y}" if event.x else None,
                "target_text": None,
                "payload": {
                    "x": event.x,
                    "y": event.y,
                    "device_id": event.device_id,
                    "platform": "android"
                }
            })

        return trace_events
