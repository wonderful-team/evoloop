"""Voice session state machine for full-duplex dialogue.

Tracks per-thread state transitions driven by Tauri-side voice signals:
  idle → listening → processing → speaking → idle
                                ↘ interrupted → listening

The state machine is in-process (single desktop app, no Redis needed).
All transitions are validated — illegal jumps are logged and ignored.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class VoiceSessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


_VALID_TRANSITIONS: dict[VoiceSessionState, set[VoiceSessionState]] = {
    VoiceSessionState.IDLE: {
        VoiceSessionState.LISTENING,
    },
    VoiceSessionState.LISTENING: {
        VoiceSessionState.PROCESSING,
        VoiceSessionState.IDLE,
    },
    VoiceSessionState.PROCESSING: {
        VoiceSessionState.SPEAKING,
        VoiceSessionState.IDLE,
    },
    VoiceSessionState.SPEAKING: {
        VoiceSessionState.IDLE,
        VoiceSessionState.INTERRUPTED,
    },
    VoiceSessionState.INTERRUPTED: {
        VoiceSessionState.LISTENING,
        VoiceSessionState.IDLE,
    },
}


class VoiceSessionStateMachine:
    """Per-thread voice session state tracker."""

    def __init__(self) -> None:
        self._states: dict[str, VoiceSessionState] = {}
        self._lock = asyncio.Lock()

    async def get(self, thread_id: str) -> VoiceSessionState:
        async with self._lock:
            return self._states.get(thread_id, VoiceSessionState.IDLE)

    async def set(self, thread_id: str, new_state: VoiceSessionState) -> bool:
        async with self._lock:
            current = self._states.get(thread_id, VoiceSessionState.IDLE)
            allowed = _VALID_TRANSITIONS.get(current, set())
            if new_state not in allowed:
                logger.warning(
                    "[voice-sm] illegal transition %s → %s for thread %s",
                    current.value,
                    new_state.value,
                    thread_id,
                )
                return False
            self._states[thread_id] = new_state
            logger.debug(
                "[voice-sm] %s: %s → %s",
                thread_id,
                current.value,
                new_state.value,
            )
            return True

    async def force_set(self, thread_id: str, new_state: VoiceSessionState) -> None:
        async with self._lock:
            self._states[thread_id] = new_state

    async def clear(self, thread_id: str) -> None:
        async with self._lock:
            self._states.pop(thread_id, None)

    async def is_speaking(self, thread_id: str) -> bool:
        async with self._lock:
            return self._states.get(thread_id) == VoiceSessionState.SPEAKING

    async def can_accept_route(self, thread_id: str) -> bool:
        async with self._lock:
            state = self._states.get(thread_id, VoiceSessionState.IDLE)
            return state in (VoiceSessionState.IDLE, VoiceSessionState.LISTENING, VoiceSessionState.INTERRUPTED)

    async def snapshot(self) -> dict[str, str]:
        async with self._lock:
            return {k: v.value for k, v in self._states.items()}


voice_state_machine = VoiceSessionStateMachine()
