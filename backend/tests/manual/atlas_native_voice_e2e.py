"""真语音全链 E2E：say 合成语音 -> sherpa-onnx ASR（客户端同款模型）->
voice.route ws -> 原生宏真实执行。

    .venv/bin/python tests/manual/atlas_native_voice_e2e.py

自残守卫：只选无害宏（关于面板/新标签页）；绝不触发退出类。
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend")

WS_PORT = 18312
WS_URL = f"ws://127.0.0.1:{WS_PORT}/api/v1/voice/ws"
MODEL_DIR = os.path.expanduser(
    "~/.config/models/sherpa-onnx/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
)
TMP = "/tmp/atlas_voice_e2e"

# (说的话, 期望宏名片段) —— 全部无害
CASES = [
    ("关于微信", "关于微信"),
    ("新建标签页", "新标签页"),
]


def synthesize(text: str, idx: int) -> str:
    os.makedirs(TMP, exist_ok=True)
    aiff = f"{TMP}/{idx}.aiff"
    wav = f"{TMP}/{idx}.wav"
    subprocess.run(["say", "-v", "Tingting", "-o", aiff, text], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", aiff, wav],
        check=True,
    )
    return wav


def transcribe(recognizer, wav: str) -> str:
    import wave

    import numpy as np

    stream = recognizer.create_stream()
    with wave.open(wav, "rb") as f:
        sr = f.getframerate()
        samples = (
            np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)
            / 32768
        )
    stream.accept_waveform(sr, samples)
    stream.accept_waveform(sr, np.zeros(int(0.66 * sr), dtype=np.float32))
    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_streams([stream])
    return recognizer.get_result(stream).strip()


def make_recognizer():
    import sherpa_onnx

    return sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=f"{MODEL_DIR}/tokens.txt",
        encoder=f"{MODEL_DIR}/encoder-epoch-99-avg-1.int8.onnx",
        decoder=f"{MODEL_DIR}/decoder-epoch-99-avg-1.int8.onnx",
        joiner=f"{MODEL_DIR}/joiner-epoch-99-avg-1.int8.onnx",
        num_threads=1,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
    )


def _envelope(type_: str, body: dict) -> dict:
    return {
        "version": "2.0",
        "type": type_,
        "message_id": uuid.uuid4().hex,
        "timestamp": int(time.time()),
        "body": body,
    }


async def _recv_until(ws, pred, timeout: float, label: str) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(label)
        data = await asyncio.wait_for(ws.recv(), timeout=left)
        env = json.loads(data)
        body = env.get("body") or env
        if env.get("type") == "voice.route_result" and pred(body):
            return body


async def _macro_name(macro_id: int) -> str:
    from sqlalchemy import select

    from app.infrastructure.database import session_scope
    from app.models.macro import Macro

    async with session_scope() as db:
        m = (await db.execute(select(Macro).where(Macro.id == macro_id))).scalar_one_or_none()
        return m.name if m else "?"


async def main() -> None:
    import uvicorn
    import websockets

    from app.infrastructure.database.resource_manager import db_resource_manager
    from app.main import app

    await db_resource_manager.initialize(create_tables=False, seed_data=False)
    print("[asr] 装载 sherpa-onnx streaming zipformer（客户端同款）")
    recognizer = make_recognizer()

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=WS_PORT, log_level="error")
    )
    serve_task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.2)

    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.recv()  # system.init
            for i, (spoken, expect_frag) in enumerate(CASES):
                wav = synthesize(spoken, i)
                t0 = time.monotonic()
                text = await asyncio.to_thread(transcribe, recognizer, wav)
                asr_ms = (time.monotonic() - t0) * 1000
                print(f"\n[case] 说: {spoken!r} -> ASR({asr_ms:.0f}ms): {text!r}")
                if not text:
                    print("  FAIL: ASR 空结果")
                    continue

                thread = f"voice-e2e-{i}"
                t1 = time.monotonic()
                await ws.send(
                    json.dumps(_envelope("voice.route", {"thread_id": thread, "text": text}))
                )
                decision = await _recv_until(
                    ws, lambda b, t=thread: b.get("thread_id") == t and "status" in b, 120, "decision"
                )
                route_ms = (time.monotonic() - t1) * 1000
                target = decision.get("target") or {}
                print(f"  路由({route_ms:.0f}ms): {decision.get('status')} -> {target}")
                if decision.get("status") != "routed" or target.get("type") != "macro":
                    print("  FAIL: 未路由到宏")
                    continue

                result = await _recv_until(
                    ws, lambda b, t=thread: b.get("thread_id") == t and "summary" in b, 120, "result"
                )
                got_name = await _macro_name(target["id"])
                print(f"  执行: {result.get('status')} | 宏: {got_name}")
                ok = result.get("status") == "done" and expect_frag in got_name
                print(f"  {'PASS' if ok else 'FAIL'}（期望宏含 {expect_frag!r}）")
    finally:
        server.should_exit = True
        await serve_task
        await db_resource_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
