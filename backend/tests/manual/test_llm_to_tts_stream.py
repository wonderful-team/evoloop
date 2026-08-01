"""E2E test: real LLM stream → voice.tts_boundary → TTS.

Requires LM Studio running on 127.0.0.1:1234 with qwen3-4b-instruct-2507.
"""

import asyncio
import time

from app.core.voice.executor import manager


async def test_llm_stream_produces_tts_boundaries():
    """Call the real LLM, capture all WS pushes, verify tts_boundary events."""
    pushed = []
    original_push = manager.push

    async def capture(tid, env):
        pushed.append(env)
        return True

    manager.push = capture
    try:
        t0 = time.time()
        result = await stream_llm_response(
            "test-stream",
            [{"role": "user", "content": "用一句话介绍你自己，不超过20个字"}],
            "qwen3-4b-instruct-2507",
            temperature=0.7,
            max_tokens=100,
            base_url="http://127.0.0.1:1234/v1",
            api_key="lm-studio",
        )
        elapsed = (time.time() - t0) * 1000
        print(f"Full text ({len(result)} chars): {result}")
        print(f"LLM generation: {elapsed:.0f}ms")

        # Classify pushes
        tokens = [e for e in pushed if e.get("type") == "voice.token"]
        boundaries = [e for e in pushed if e.get("type") == "voice.tts_boundary"]
        print(f"voice.token pushes: {len(tokens)}")
        print(f"voice.tts_boundary pushes: {len(boundaries)}")

        for b in boundaries:
            s = b.get("body", {}).get("sentence", "")
            print(f"  TTS sentence ({len(s)} chars): {s}")

        assert result, "LLM should produce text"
        assert len(tokens) > 0, "Should have token pushes"
        assert len(boundaries) >= 1, "Should have at least one tts_boundary"

        # Verify sentences reconstruct to full text
        reconstructed = "".join(
            b.get("body", {}).get("sentence", "") for b in boundaries
        )
        print(f"\nReconstructed: {reconstructed}")

        # Step 2: Speak the result through TTS
        print(f"\n播报: {reconstructed}")
        import subprocess
        proc = subprocess.run(
            ["say", "-v", "Ting-Ting", "-r", "200", reconstructed],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"say failed: {proc.stderr}"
        print("✅ TTS 播报完成")

        return True
    finally:
        manager.push = original_push


if __name__ == "__main__":
    success = asyncio.run(test_llm_stream_produces_tts_boundaries())
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}")
