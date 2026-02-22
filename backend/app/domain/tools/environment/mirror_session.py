"""
Mirror Session Manager - Handles scrcpy processes for Android mirroring.
"""

import asyncio
import logging
import subprocess
import threading

logger = logging.getLogger(__name__)


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

    async def start(self, bitrate: str = "2M", max_fps: int = 30) -> bool:
        """
        Start scrcpy for this session.
        By default, it opens a local window. 
        In future iterations, we can use --no-display and stream to a socket.
        """
        try:
            # Check if scrcpy is installed
            result = subprocess.run(["scrcpy", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                self.error = "scrcpy not found. Please install it with 'brew install scrcpy'."
                return False

            cmd = [
                "scrcpy",
                "-s", self.device_id,
                "--window-title", f"EvoLoop Mirror - {self.device_id}",
                "--video-bit-rate", bitrate,
                "--max-fps", str(max_fps),
                "--always-on-top"
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

            return True

        except Exception as e:
            self.error = str(e)
            logger.error(f"Failed to start scrcpy: {e}")
            return False

    def stop(self):
        """Terminate the scrcpy process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        self.is_active = False
        self.should_be_active = False  # Manual stop clears intention
        logger.info(f"Stopped mirror session {self.session_id}")


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

    def stop_session(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session:
            session.stop()
            return True
        return False

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
                # Mark as inactive but keep should_be_active if desired
                # processes die automatically on disconnect anyway
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
