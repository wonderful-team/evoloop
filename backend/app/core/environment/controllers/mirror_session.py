"""
Mirror Session Manager — Handles scrcpy processes for Android mirroring.
"""

import asyncio
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from pydantic import Field

from app.core.config import settings
from app.infrastructure.pydantic_base import DynamicBaseModel
from .android_event_recorder import AndroidEventRecorder, AndroidTraceEvent

logger = logging.getLogger(__name__)

# Android recordings directory (from settings)
ANDROID_RECORDINGS_DIR = Path(settings.ANDROID_RECORDINGS_DIR)


class MirrorSessionStopResult(DynamicBaseModel):
    video_path: str | None = None
    events: list[AndroidTraceEvent] = Field(default_factory=list)
    session_id: str


class MirrorSession:
    """
    Represents a single active scrcpy mirroring session.
    """
    def __init__(self, session_id: str, device_id: str):
        self.session_id = session_id
        self.device_id = device_id
        self.process: subprocess.Popen | None = None
        self.is_active = False

        # Video timestamp synchronization
        self._video_start_time: float | None = None  # Unix timestamp when video recording started
        self.port: int | None = None
        self.error: str | None = None
        self.should_be_active = False  # Persists through disconnects
        self.video_path: str | None = None  # Path to recorded video file

        # Real-time event persistence
        self.event_recorder: AndroidEventRecorder | None = None
        self._recording_started = False
        self.captured_events: list[AndroidTraceEvent] = []
        self._event_queue = asyncio.Queue()
        self._persist_task = None
        self._step_counter = 0

    async def _persist_loop(self):
        """
        Background task to persist events to DB in real-time.

        Events are persisted immediately to unify with global/DOM recording flow.
        This ensures events are not lost if backend restarts.
        """
        logger.info(f"[MirrorSession] Started real-time event persistence for session {self.session_id}")
        batch_buffer = []
        BATCH_SIZE = 10  # Persist every 10 events or 1 second

        while self.is_active or not self._event_queue.empty() or batch_buffer:
            try:
                # Use a timeout to flush batch periodically
                try:
                    event_data = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Flush remaining batch on timeout
                    if batch_buffer:
                        await self._persist_event_batch(batch_buffer)
                        batch_buffer = []
                    continue

                self._step_counter += 1
                relative_ms = int(event_data.timestamp)

                # Create event dict
                buffered_event = {
                    "timestamp": relative_ms,
                    "event_type": event_data.event_type,
                    "source": "mobile",
                    "node_name": self.device_id,
                    "target_selector": f"android://screen/{event_data.x}/{event_data.y}" if event_data.x is not None else None,
                    "target_text": None,
                    "payload": {
                        "x": event_data.x,
                        "y": event_data.y,
                        "device_id": event_data.device_id,
                        "key_code": event_data.key_code,
                        "platform": "android",
                        "package_name": event_data.app_package,
                        "relative_timestamp_ms": relative_ms,
                    }
                }
                batch_buffer.append(buffered_event)

                # Log first few events
                if self._step_counter <= 5:
                    logger.info(f"[MirrorSession] Event {self._step_counter}: {event_data.event_type} at {relative_ms}ms (device_id={event_data.device_id}, package={event_data.app_package})")

                # Persist batch when size reached
                if len(batch_buffer) >= BATCH_SIZE:
                    await self._persist_event_batch(batch_buffer)
                    batch_buffer = []

                self._event_queue.task_done()
            except Exception as e:
                logger.error(f"[MirrorSession] Failed to persist event: {e}")
                await asyncio.sleep(1)

        # Final flush
        if batch_buffer:
            await self._persist_event_batch(batch_buffer)

    async def _persist_event_batch(self, events: list[AndroidTraceEvent]):
        """Persist a batch of events to database."""
        import json

        from app.infrastructure.database.sql.database import session_scope
        from app.models import TraceEvent

        if not events:
            return

        try:
            async with session_scope() as db:
                for event_data in events:
                    payload = event_data.get("payload", {})
                    trace_event = TraceEvent(
                        session_id=self.session_id,
                        recording_session_id=self.session_id,
                        thread_id="global",  # Mirror sessions use global thread
                        step_number=self._step_counter - len(events) + events.index(event_data) + 1,
                        node_name=payload.get("node_name", self.device_id),
                        action_type="user_interaction",
                        timestamp=event_data["timestamp"],
                        event_type=event_data["event_type"],
                        target_selector=event_data.get("target_selector"),
                        target_text=event_data.get("target_text"),
                        payload=payload,
                        mouse_x=payload.get("x"),
                        mouse_y=payload.get("y"),
                        source="mobile",
                        app_name=payload.get("package_name"),
                        state_snapshot=json.dumps({"context": "android_mirror"}),
                        action_payload=json.dumps(payload)
                    )
                    db.add(trace_event)
            logger.debug(f"[MirrorSession] Persisted {len(events)} events to DB")
        except Exception as e:
            logger.error(f"[MirrorSession] Failed to persist batch: {e}")
            raise

    async def start(self, bitrate: str = "2M", max_fps: int = 30, record_video: bool = True) -> bool:
        """
        Start scrcpy for this session with optional video recording.
        """
        try:
            # Check if scrcpy is installed
            result = subprocess.run(["scrcpy", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                self.error = "scrcpy not found. Please install it with 'brew install scrcpy'."
                return False

            # Set up video recording path (organized by device)
            cmd = [
                "scrcpy",
                "-s", self.device_id,
                "--window-title", f"EvoLoop Mirror - {self.device_id}",
                "--video-bit-rate", bitrate,
                "--max-fps", str(max_fps),
                "--always-on-top",
            ]

            if record_video:
                device_dir = ANDROID_RECORDINGS_DIR / self.device_id.replace(":", "_")
                device_dir.mkdir(parents=True, exist_ok=True)
                self.video_path = str(device_dir / f"{self.session_id}.mp4")
                cmd.extend([
                    "--record", self.video_path,
                    "--record-format", "mp4"
                ])

            # Start process in background
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Record video start time immediately after process starts
            self._video_start_time = time.time()
            logger.info(f"[MirrorSession] scrcpy process started, video recording begins at {self._video_start_time}")

            # Wait a bit to see if it crashes
            await asyncio.sleep(1.0)
            if self.process.poll() is not None:
                _, stderr = self.process.communicate()
                self.error = stderr.strip()
                logger.error(f"scrcpy failed immediately: {self.error}")
                self.is_active = False
                return False

            self.is_active = True
            self.should_be_active = True
            logger.info(f"Started scrcpy session {self.session_id} for device {self.device_id}")

            # Start recording immediately to ensure synchronization
            if record_video:
                self.start_recording()
                logger.info(f"Automatic event recording started for session {self.session_id}")

            # Persist loop for real-time event persistence
            self._persist_task = asyncio.create_task(self._persist_loop())

            # Thread to log output and detect recording start
            def log_output():
                if self.process and self.process.stderr:
                    for line in self.process.stderr:
                        clean_line = line.strip()
                        logger.debug(f"[scrcpy {self.device_id}] {clean_line}")

                        # Look for recording start confirmation
                        if "Recording to" in clean_line and ".mp4" in clean_line:
                            exact_start = time.time()
                            self._video_start_time = exact_start
                            logger.info(f"[MirrorSession] scrcpy confirmed recording start at {exact_start}")

                            # If recorder is already running, update its sync clock
                            if self.event_recorder:
                                self.event_recorder.set_video_start_time(exact_start)

            threading.Thread(target=log_output, daemon=True).start()

            return True

        except Exception as e:
            self.error = str(e)
            logger.error(f"Failed to start scrcpy: {e}")
            return False

    def start_recording(self) -> bool:
        """
        Start Android event recording.

        Events are synchronized to video start time for accurate keyframe extraction.
        """
        if not self.is_active:
            return False

        if self._recording_started and self.event_recorder:
            return True

        try:
            self.event_recorder = AndroidEventRecorder()

            loop = asyncio.get_running_loop()
            def on_event(event):
                loop.call_soon_threadsafe(self._event_queue.put_nowait, event)

            self.event_recorder.start_recording(
                self.device_id,
                callback=on_event,
                video_start_time=self._video_start_time
            )
            self._recording_started = True
            logger.info(f"[MirrorSession] Event recording started with video_start_time={self._video_start_time}")

            logger.info(f"[MirrorSession] Started Android event recording for session {self.session_id}")
            return True

        except Exception as e:
            logger.error(f"[MirrorSession] Failed to start recording: {e}")
            return False

    def get_current_package(self) -> str | None:
        """Get the current active app package on the device."""
        if self.event_recorder:
            return self.event_recorder.get_current_package(self.device_id)

        # Fallback if recorder not initialized
        recorder = AndroidEventRecorder()
        return recorder.get_current_package(self.device_id)

    def stop(self) -> MirrorSessionStopResult | None:
        """
        Terminate the scrcpy process and stop event recording.
        Returns result with video_path and events (events are already persisted in real-time via _persist_loop).
        """
        # Stop event recording first
        captured_events: list[AndroidTraceEvent] = []
        if self.event_recorder and self._recording_started:
            android_events = self.event_recorder.stop_recording()
            captured_events = self.event_recorder.to_trace_events(
                session_id=self.session_id,
                thread_id="global"
            )
            self.captured_events = captured_events
            logger.info(f"Stopped event recording. Captured {len(captured_events)} events")

        # Stop scrcpy
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None

        self.is_active = False
        self.should_be_active = False  # Manual stop clears intention

        # Stop persist task
        if self._persist_task:
            self._persist_task.cancel()
            self._persist_task = None

        # Verify video file exists
        video_path = self.video_path
        if video_path and os.path.exists(video_path):
            logger.info(f"Mirror session {self.session_id} stopped. Video saved to: {video_path}")
            return MirrorSessionStopResult(
                video_path=video_path,
                events=captured_events,
                session_id=self.session_id
            )
        else:
            logger.warning(f"Mirror session {self.session_id} stopped but video file not found: {video_path}")
            return None


class MirrorSessionManager:
    """
    Manages multiple mirroring sessions.
    """
    def __init__(self):
        self.sessions: dict[str, MirrorSession] = {}
        self.stopped_sessions: dict[str, MirrorSession] = {}  # Cache stopped sessions for event count retrieval

    async def create_session(self, device_id: str, record_video: bool = True) -> MirrorSession:
        from app.utils.id import gen_uuid
        session_id = gen_uuid()
        session = MirrorSession(session_id, device_id)

        success = await session.start(record_video=record_video)
        if success:
            self.sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> MirrorSession | None:
        return self.sessions.get(session_id) or self.stopped_sessions.get(session_id)

    def start_recording(self, session_id: str) -> bool:
        """
        Start event recording for an active session.
        Called when user clicks 'Start Recording'.
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"[MirrorManager] Cannot start recording: session {session_id} not found")
            return False

        return session.start_recording()

    def stop_session(self, session_id: str) -> MirrorSessionStopResult | None:
        """Stop session and return video path and events."""
        session = self.sessions.pop(session_id, None)
        if session:
            result = session.stop()
            # Cache the stopped session for event retrieval during persistence
            self.stopped_sessions[session_id] = session

            # Limit cache size
            if len(self.stopped_sessions) > 50:
                oldest_key = next(iter(self.stopped_sessions))
                self.stopped_sessions.pop(oldest_key)

            return result
        return None

    def get_session_events(self, session_id: str) -> list[AndroidTraceEvent]:
        """Get captured events for a session (for reference; events are already persisted in real-time)."""
        session = self.get_session(session_id)
        if session:
            return session.captured_events
        return []

    async def on_device_connected(self, device_id: str):
        """Handle device reconnection."""
        for session in self.sessions.values():
            if session.device_id == device_id and session.should_be_active and not session.is_active:
                logger.info(f"Attempting to recover mirror session for {device_id}...")
                await session.start()

    def on_device_disconnected(self, device_id: str):
        """Handle device disconnection."""
        for session in self.sessions.values():
            if session.device_id == device_id:
                session.is_active = False
                session.should_be_active = False
                if session.process:
                    session.process.terminate()
                    session.process = None

    def cleanup(self):
        """Stop all active sessions."""
        for session in list(self.sessions.values()):
            session.stop()
        self.sessions.clear()


# Global Manager Instance
mirror_manager = MirrorSessionManager()
