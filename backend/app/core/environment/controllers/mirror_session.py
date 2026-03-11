"""
Mirror Session Manager — Handles scrcpy processes for Android mirroring.
"""

import asyncio
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from app.core.config import settings
from .android_event_recorder import AndroidEventRecorder

logger = logging.getLogger(__name__)

# Android recordings directory (from settings)
ANDROID_RECORDINGS_DIR = Path(settings.ANDROID_RECORDINGS_DIR)


class MirrorSession:
    """
    Represents a single active scrcpy mirroring session.
    """
    def __init__(self, session_id: str, device_id: str):
        self.session_id = session_id
        self.device_id = device_id
        self.process: subprocess.Popen | None = None
        self.is_active = False
        self.port: int | None = None
        self.error: str | None = None
        self.should_be_active = False  # Persists through disconnects
        self.video_path: str | None = None  # Path to recorded video file

        # [FIX] Delayed recording: event_recorder is now created on start_recording(), not on session start
        self.event_recorder: AndroidEventRecorder | None = None  # Android event recorder
        self._recording_started = False  # [NEW] Track if user has started recording
        self.captured_events: list[dict] = []  # Captured events (local storage before persistence)
        self._event_queue = asyncio.Queue()
        self._persist_task = None
        self._step_counter = 0

    async def _persist_loop(self):
        """
        Background task to buffer captured events (NO LONGER persists to DB in real-time).

        [FIX] Changed from real-time persistence to in-memory buffering only.
        Events are persisted when stop() is called or via persist_mirror_events().
        This avoids duplicate events in database.
        """
        logger.info(f"[MirrorSession] Started event buffering for session {self.session_id} (real-time persistence disabled)")
        while self.is_active or not self._event_queue.empty():
            try:
                # Use a timeout to occasionally check if we should stop
                try:
                    event_data = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # [FIX] Just buffer the event in memory, don't persist to DB yet
                self._step_counter += 1
                # [FIX] event_data.timestamp is already in milliseconds from AndroidEventRecorder
                relative_ms = int(event_data.timestamp)

                # Create event dict for later persistence
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
                self.captured_events.append(buffered_event)

                # Log first few events for debugging
                if self._step_counter <= 5:
                    logger.info(f"[MirrorSession] Buffered event {self._step_counter}: {event_data.event_type} at {relative_ms}ms (device_id={event_data.device_id}, package={event_data.app_package})")

                self._event_queue.task_done()
            except Exception as e:
                logger.error(f"[MirrorSession] Failed to buffer event: {e}")
                await asyncio.sleep(1)

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

            # [FIX] Start recording immediately to ensure synchronization
            if record_video:
                self.start_recording()
                logger.info(f"Automatic event recording started for session {self.session_id}")

            # [FIX] Persist loop is still needed for when recording starts
            self._persist_task = asyncio.create_task(self._persist_loop())

            # Thread to log output
            def log_output():
                if self.process and self.process.stderr:
                    for line in self.process.stderr:
                        logger.debug(f"[scrcpy {self.device_id}] {line.strip()}")

            threading.Thread(target=log_output, daemon=True).start()

            return True

        except Exception as e:
            self.error = str(e)
            logger.error(f"Failed to start scrcpy: {e}")
            return False

    def start_recording(self) -> bool:
        """
        [NEW] Start Android event recording when user clicks 'Start Recording'.
        This is separate from mirror session start to allow delayed recording.
        """
        if not self.is_active:
            return False

        if self._recording_started and self.event_recorder:
            return True

        try:
            # Create and start event recorder
            self.event_recorder = AndroidEventRecorder()

            # Bridge thread to asyncio loop
            loop = asyncio.get_running_loop()
            def on_event(event):
                # Use call_soon_threadsafe because the recorder runs in a separate thread
                loop.call_soon_threadsafe(self._event_queue.put_nowait, event)

            self.event_recorder.start_recording(self.device_id, callback=on_event)
            self._recording_started = True

            logger.info(f"[MirrorSession] Started Android event recording for session {self.session_id}")
            return True

        except Exception as e:
            logger.error(f"[MirrorSession] Failed to start recording: {e}")
            return False

    def stop(self) -> dict[str, Any] | None:
        """
        Terminate the scrcpy process and stop event recording.
        Returns dict with video_path and events (local storage, not yet persisted).
        """
        # Stop event recording first
        captured_events = []
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
            return {
                "video_path": video_path,
                "events": captured_events,
                "session_id": self.session_id
            }
        else:
            logger.warning(f"Mirror session {self.session_id} stopped but video file not found: {video_path}")
            return None


class MirrorSessionManager:
    """
    Manages multiple mirroring sessions.
    """
    def __init__(self):
        self.sessions: dict[str, MirrorSession] = {}
        self.stopped_sessions: dict[str, MirrorSession] = {}  # Cache stopped sessions for persistence

    async def create_session(self, device_id: str, record_video: bool = True) -> MirrorSession:
        import uuid
        session_id = str(uuid.uuid4())
        session = MirrorSession(session_id, device_id)

        success = await session.start(record_video=record_video)
        if success:
            self.sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> MirrorSession | None:
        return self.sessions.get(session_id) or self.stopped_sessions.get(session_id)

    def start_recording(self, session_id: str) -> bool:
        """
        [NEW] Start event recording for an active session.
        Called when user clicks 'Start Recording'.
        """
        session = self.sessions.get(session_id)
        if not session:
            logger.error(f"[MirrorManager] Cannot start recording: session {session_id} not found")
            return False

        return session.start_recording()

    def stop_session(self, session_id: str) -> dict[str, Any] | None:
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

    def get_session_events(self, session_id: str) -> list[dict]:
        """Get captured events for a session (for delayed persistence)."""
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
