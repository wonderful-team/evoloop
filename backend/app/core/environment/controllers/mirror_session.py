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

from .android_event_recorder import AndroidEventRecorder

logger = logging.getLogger(__name__)

# Recording directory (same as screen recording)
RECORDINGS_DIR = Path.home() / ".evoloop" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

# Android recordings subdirectory
ANDROID_RECORDINGS_DIR = RECORDINGS_DIR / "android"
ANDROID_RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)


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
        self.event_recorder: AndroidEventRecorder | None = None  # Android event recorder
        self.captured_events: list[dict] = []  # Captured events (local storage before persistence)

    async def start(self, bitrate: str = "2M", max_fps: int = 30) -> bool:
        """
        Start scrcpy for this session with video recording.
        """
        try:
            # Check if scrcpy is installed
            result = subprocess.run(["scrcpy", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                self.error = "scrcpy not found. Please install it with 'brew install scrcpy'."
                return False

            # Set up video recording path (organized by device)
            device_dir = ANDROID_RECORDINGS_DIR / self.device_id.replace(":", "_")
            device_dir.mkdir(parents=True, exist_ok=True)
            self.video_path = str(device_dir / f"{self.session_id}.mp4")

            cmd = [
                "scrcpy",
                "-s", self.device_id,
                "--window-title", f"EvoLoop Mirror - {self.device_id}",
                "--video-bit-rate", bitrate,
                "--max-fps", str(max_fps),
                "--always-on-top",
                "--record", self.video_path,  # Enable video recording
                "--record-format", "mp4"
            ]

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

            # Thread to log output
            def log_output():
                if self.process and self.process.stderr:
                    for line in self.process.stderr:
                        logger.debug(f"[scrcpy {self.device_id}] {line.strip()}")

            threading.Thread(target=log_output, daemon=True).start()

            # Start Android event recording
            self.event_recorder = AndroidEventRecorder()
            self.event_recorder.start_recording(self.device_id)
            logger.info(f"Started Android event recording for session {self.session_id}")

            return True

        except Exception as e:
            self.error = str(e)
            logger.error(f"Failed to start scrcpy: {e}")
            return False

    def stop(self) -> dict[str, Any] | None:
        """
        Terminate the scrcpy process and stop event recording.
        Returns dict with video_path and events (local storage, not yet persisted).
        """
        # Stop event recording first
        captured_events = []
        if self.event_recorder:
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

    async def create_session(self, device_id: str) -> MirrorSession:
        import uuid
        session_id = str(uuid.uuid4())
        session = MirrorSession(session_id, device_id)

        success = await session.start()
        if success:
            self.sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> MirrorSession | None:
        return self.sessions.get(session_id)

    def stop_session(self, session_id: str) -> dict[str, Any] | None:
        """Stop session and return video path and events."""
        session = self.sessions.pop(session_id, None)
        if session:
            return session.stop()
        return None

    def get_session_events(self, session_id: str) -> list[dict]:
        """Get captured events for a session (for delayed persistence)."""
        session = self.sessions.get(session_id)
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
