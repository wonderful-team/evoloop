"""Tests for VoiceSessionStateMachine."""

import pytest

from app.core.voice.state_machine import (
    VoiceSessionState,
    VoiceSessionStateMachine,
)


@pytest.fixture
def sm() -> VoiceSessionStateMachine:
    return VoiceSessionStateMachine()


@pytest.mark.asyncio
async def test_default_state_is_idle(sm: VoiceSessionStateMachine) -> None:
    assert await sm.get("thread-1") == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_valid_transition_idle_to_listening(sm: VoiceSessionStateMachine) -> None:
    assert await sm.set("thread-1", VoiceSessionState.LISTENING) is True
    assert await sm.get("thread-1") == VoiceSessionState.LISTENING


@pytest.mark.asyncio
async def test_valid_transition_listening_to_processing(sm: VoiceSessionStateMachine) -> None:
    await sm.set("thread-1", VoiceSessionState.LISTENING)
    assert await sm.set("thread-1", VoiceSessionState.PROCESSING) is True
    assert await sm.get("thread-1") == VoiceSessionState.PROCESSING


@pytest.mark.asyncio
async def test_valid_transition_processing_to_speaking(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("thread-1", VoiceSessionState.PROCESSING)
    assert await sm.set("thread-1", VoiceSessionState.SPEAKING) is True


@pytest.mark.asyncio
async def test_valid_transition_speaking_to_interrupted(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("thread-1", VoiceSessionState.SPEAKING)
    assert await sm.set("thread-1", VoiceSessionState.INTERRUPTED) is True
    assert await sm.get("thread-1") == VoiceSessionState.INTERRUPTED


@pytest.mark.asyncio
async def test_valid_transition_interrupted_to_listening(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("thread-1", VoiceSessionState.INTERRUPTED)
    assert await sm.set("thread-1", VoiceSessionState.LISTENING) is True


@pytest.mark.asyncio
async def test_illegal_transition_idle_to_speaking(sm: VoiceSessionStateMachine) -> None:
    assert await sm.set("thread-1", VoiceSessionState.SPEAKING) is False
    assert await sm.get("thread-1") == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_illegal_transition_listening_to_speaking(sm: VoiceSessionStateMachine) -> None:
    await sm.set("thread-1", VoiceSessionState.LISTENING)
    assert await sm.set("thread-1", VoiceSessionState.SPEAKING) is False
    assert await sm.get("thread-1") == VoiceSessionState.LISTENING


@pytest.mark.asyncio
async def test_force_set_bypasses_validation(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("thread-1", VoiceSessionState.SPEAKING)
    assert await sm.get("thread-1") == VoiceSessionState.SPEAKING


@pytest.mark.asyncio
async def test_clear(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("thread-1", VoiceSessionState.LISTENING)
    await sm.clear("thread-1")
    assert await sm.get("thread-1") == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_is_speaking(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("thread-1", VoiceSessionState.SPEAKING)
    assert await sm.is_speaking("thread-1") is True
    assert await sm.is_speaking("thread-2") is False


@pytest.mark.asyncio
async def test_can_accept_route(sm: VoiceSessionStateMachine) -> None:
    assert await sm.can_accept_route("thread-1") is True
    await sm.force_set("thread-1", VoiceSessionState.PROCESSING)
    assert await sm.can_accept_route("thread-1") is False
    await sm.force_set("thread-1", VoiceSessionState.INTERRUPTED)
    assert await sm.can_accept_route("thread-1") is True


@pytest.mark.asyncio
async def test_full_cycle(sm: VoiceSessionStateMachine) -> None:
    """idle → listening → processing → speaking → idle"""
    assert await sm.set("t", VoiceSessionState.LISTENING) is True
    assert await sm.set("t", VoiceSessionState.PROCESSING) is True
    assert await sm.set("t", VoiceSessionState.SPEAKING) is True
    assert await sm.set("t", VoiceSessionState.IDLE) is True


@pytest.mark.asyncio
async def test_barge_in_cycle(sm: VoiceSessionStateMachine) -> None:
    """idle → listening → processing → speaking → interrupted → listening"""
    await sm.force_set("t", VoiceSessionState.SPEAKING)
    assert await sm.set("t", VoiceSessionState.INTERRUPTED) is True
    assert await sm.set("t", VoiceSessionState.LISTENING) is True


@pytest.mark.asyncio
async def test_snapshot(sm: VoiceSessionStateMachine) -> None:
    await sm.force_set("t1", VoiceSessionState.LISTENING)
    await sm.force_set("t2", VoiceSessionState.SPEAKING)
    snap = await sm.snapshot()
    assert snap["t1"] == "listening"
    assert snap["t2"] == "speaking"
