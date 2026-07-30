"""Validate voice_receive_loop fix: generation counter, disconnect handling.

See AGENTS.md work state for the race condition:
  The old voice_receive_loop task could call websocket.close(code=1011) after
  voice.start closes the Volcengine client, which closes the shared WS and
  kills the main loop with "Cannot call receive once a disconnect...".
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from app.api.routes import voice_ws as vw_module
from app.api.routes.voice_ws import (
    voice_receive_loop,
    _volc_gen,
    _last_asr_text,
    _is_sending_chat_tts_text,
)
from app.core.voice.state_machine import voice_state_machine, VoiceSessionState


@pytest.mark.asyncio
async def test_generation_counter_prevents_stale_cleanup():
    """A stale task (gen=N) must NOT clear state when gen has moved to N+1."""
    tid = "test-gen-stale"
    fake_ws = AsyncMock()
    fake_client = AsyncMock()
    # receive_response raises immediately so the loop exits
    fake_client.receive_response.side_effect = RuntimeError("simulated")

    _volc_gen[tid] = 42   # current generation
    await voice_state_machine.set(tid, VoiceSessionState.LISTENING)

    # Run the loop with stale gen=41 — the finally must NOT clear the state
    await voice_receive_loop(fake_ws, fake_client, tid, "c-stale", "dialogue", gen=41)

    # State machine should still have LISTENING (not cleared)
    state = await voice_state_machine.get(tid)
    assert state == VoiceSessionState.LISTENING, (
        f"Stale task cleared state! Got {state}"
    )

    # Per-thread dicts should still have the entry (set by dialogue mode init)
    assert tid in _is_sending_chat_tts_text, "Stale task removed chat_tts_text!"
    assert tid not in _last_asr_text, "_last_asr_text should not be set"

    # Cleanup
    await voice_state_machine.clear(tid)
    _volc_gen.pop(tid, None)
    _is_sending_chat_tts_text.pop(tid, None)


@pytest.mark.asyncio
async def test_generation_counter_current_task_cleans_up():
    """The current task (gen matches) MUST clean up state."""
    tid = "test-gen-current"
    fake_ws = AsyncMock()
    fake_client = AsyncMock()
    fake_client.receive_response.side_effect = RuntimeError("simulated")

    _volc_gen[tid] = 7
    await voice_state_machine.set(tid, VoiceSessionState.LISTENING)

    await voice_receive_loop(fake_ws, fake_client, tid, "c-curr", "dialogue", gen=7)

    state = await voice_state_machine.get(tid)
    assert state == VoiceSessionState.IDLE, (
        f"Current task should have cleared state, got {state}"
    )

    _volc_gen.pop(tid, None)
    _is_sending_chat_tts_text.pop(tid, None)


def test_websocket_close_not_called_on_exception():
    """except Exception in voice_receive_loop must NOT call websocket.close()."""
    import inspect
    source = inspect.getsource(voice_receive_loop)
    # Find the except Exception block
    lines = source.split("\n")
    in_except = False
    for i, line in enumerate(lines):
        if "except Exception as e:" in line:
            in_except = True
            continue
        if in_except:
            if "websocket.close" in line:
                pytest.fail(
                    "voice_receive_loop still calls websocket.close()! "
                    "Line {}: {}".format(i + 1, line.strip())
                )
            # The except block is indented; dedented line means it's over
            if line and not line.startswith("        ") and not line.startswith("            "):
                break
    # If we reach here without finding websocket.close(), the fix is present


@pytest.mark.asyncio
async def test_cancel_before_close_order():
    """voice.start must cancel old task BEFORE closing old client."""
    with open(vw_module.__file__) as f:
        src = f.read()
    lines = src.split("\n")
    # Find the comment that marks the order
    order_comment = "Cancel the old receive task BEFORE closing the client"
    comment_line = next((i for i, l in enumerate(lines) if order_comment in l), -1)
    assert comment_line > 0, f"Order comment not found: {order_comment!r}"
    cancel_line = next((i for i, l in enumerate(lines[comment_line:], comment_line) if "cancel()" in l and "volc_receive_task" in l), -1)
    close_line = next((i for i, l in enumerate(lines[comment_line:], comment_line) if ".close()" in l and "volc_client" in l), -1)
    assert cancel_line > 0, "cancel() not found after comment"
    assert close_line > 0, "close() not found after comment"
    assert cancel_line < close_line, (
        f"cancel() at line {cancel_line+1} must be before close() at line {close_line+1}"
    )


@pytest.mark.asyncio
async def test_receive_loop_does_not_call_ws_close():
    """Verify voice_receive_loop's except Exception doesn't call websocket.close."""
    fake_ws = AsyncMock()
    fake_client = AsyncMock()
    fake_client.receive_response.side_effect = RuntimeError("test error")

    await voice_receive_loop(fake_ws, fake_client, "t-no-close", "c", "dialogue", gen=1)

    # websocket.close should NOT be called by the except Exception handler
    for call in fake_ws.method_calls:
        name = call[0]
        if "close" in name.lower():
            pytest.fail(f"websocket.close() was called: {call}")
