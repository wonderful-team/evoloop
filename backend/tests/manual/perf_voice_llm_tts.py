"""语音全链路性能测试：记录各节点的耗时。

用法:
    uv run python tests/manual/perf_voice_llm_tts.py [--text "你好"] [--voice zh-CN-YunxiNeural]

依赖:
    - Python 后端运行在 :20160
    - LM Studio 运行在 :1234（含 qwen3-4b-instruct-2507）
    - edge-tts 库（用于 TTS 播报）
"""

import asyncio
import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import edge_tts
import websockets

WS_URL = "ws://127.0.0.1:20160/api/v1/voice/ws"
DEFAULT_TEXT = "你好"
DEFAULT_VOICE = "zh-CN-YunxiNeural"


@dataclass
class PerfTiming:
    label: str
    elapsed_ms: float
    detail: str = ""


@dataclass
class PerfResult:
    timings: list[PerfTiming] = field(default_factory=list)
    text: str = ""
    token_count: int = 0
    boundary_count: int = 0
    sentences: list[str] = field(default_factory=list)

    def milestone(self, label: str, t_current: float, detail: str = ""):
        elapsed = (t_current - self._t0) * 1000
        self.timings.append(PerfTiming(label=label, elapsed_ms=elapsed, detail=detail))
        return elapsed

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"  测试文本: \"{self.text}\"")
        print(f"{'='*60}")
        print(f"{'节点':<35} {'耗时(ms)':>10}  {'说明'}")
        print(f"{'-'*60}")
        for t in self.timings:
            print(f"{t.label:<35} {t.elapsed_ms:>8.0f}ms  {t.detail}")
        print(f"{'-'*60}")

        ttfb = next((t for t in self.timings if t.label == "首句 TTS 收到"), None)
        done = next((t for t in self.timings if t.label == "Agent 完成"), None)

        print(f"\n  首句 TTS (TTFB):   {ttfb.elapsed_ms:>8.0f}ms  ← 用户听到第一次回应" if ttfb else "")
        print(f"  Agent 完成:        {done.elapsed_ms:>8.0f}ms" if done else "")
        print(f"  Token 数:          {self.token_count:>8}")
        print(f"  TTS 句子数:        {self.boundary_count:>8}")
        print(f"  TTS 引擎:          {DEFAULT_VOICE}")
        ok = ttfb is not None and ttfb.elapsed_ms < 3000
        print(f"\n  {'✅ PASS' if ok else '❌ FAIL'} (TTFB {'<' if ok else '>'} 3000ms)")
        return ok


async def run_test(text: str = DEFAULT_TEXT, voice: str = DEFAULT_VOICE) -> PerfResult:
    result = PerfResult(text=text)
    result._t0 = time.time()

    # ── WS 连接 ─────────────────────────────────────────────
    ws = await websockets.connect(WS_URL)
    init = json.loads(await ws.recv())
    result.milestone("WS 连接成功", time.time(),
                     f"client_id={init['body']['client_id'][:8]}...")

    tid = f"perf-{uuid.uuid4().hex[:8]}"

    await ws.send(json.dumps({
        "version": "2.0", "type": "voice.start",
        "message_id": str(uuid.uuid4()),
        "body": {"thread_id": tid},
    }))

    await ws.send(json.dumps({
        "version": "2.0", "type": "voice.route",
        "message_id": str(uuid.uuid4()),
        "body": {"thread_id": tid, "text": text},
    }))
    result.milestone("voice.route 发送", time.time())

    # ── 接收结果 ─────────────────────────────────────────────
    first_boundary = None

    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
        mtype = msg.get("type", "")
        body = msg.get("body", {})
        now = time.time()

        if mtype == "voice.token":
            result.token_count += 1
            if result.token_count == 1:
                result.milestone("首个 LLM token", now)

        elif mtype == "voice.tts_boundary":
            result.boundary_count += 1
            s = body.get("sentence", body.get("text", ""))
            result.sentences.append(s)
            label = "首句 TTS 收到" if first_boundary is None else f"后续 TTS #{result.boundary_count}"
            result.milestone(label, now, f'"{s[:50]}{"..." if len(s) > 50 else ""}"')
            if first_boundary is None:
                first_boundary = now

        elif mtype == "voice.route_result":
            status = body.get("status", "")
            if status == "routed":
                result.milestone("VoiceChannel ack", now)
            elif status in ("done", "failed"):
                result.milestone("Agent 完成", now, f"status={status}")
                break

    # ── TTS 播报 ─────────────────────────────────────────────
    for i, s in enumerate(result.sentences):
        t = time.time()
        await edge_tts.Communicate(s, voice).save("/tmp/perf_tts.mp3")
        subprocess.run(["afplay", "/tmp/perf_tts.mp3"], capture_output=True)
        label = "完整播报结束" if i == len(result.sentences) - 1 else f"TTS 合成+播放 #{i+1}"
        result.milestone(label, time.time(),
                         f'"{s[:50]}{"..." if len(s) > 50 else ""}"')

    await ws.close()
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="语音全链路性能测试")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="测试文本")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="TTS 音色")
    args = parser.parse_args()

    result = asyncio.run(run_test(text=args.text, voice=args.voice))
    ok = result.print_summary()
    exit(0 if ok else 1)
