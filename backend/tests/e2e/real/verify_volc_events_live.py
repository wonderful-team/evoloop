"""火山流式 ASR 实时打断验证脚本（需麦克风）。

实时录音 → bigmodel_async → 打印所有 event 号。
验证重点：打断场景（识别中有人插话）是否收到 event 450（barge-in）。

用法（在有麦克风的机器，backend 目录下）：
    VOLC_APP_ID=... VOLC_ACCESS_KEY=<Access Token> uv run python verify_volc_events_live.py

测试步骤：
1. 正常说话几秒 → 观察 event 451（增量）
2. 播放一段音频（模拟 Agent TTS，如 `afplay xxx.wav`）时对着麦克风说话
   → 观察是否出现 event 450（barge-in）
3. Ctrl-C 结束，看 event 统计
"""

import asyncio
import os
import sys
from collections import defaultdict

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, BACKEND_DIR)

import sounddevice as sd  # noqa: E402

from app.infrastructure.config.service import SystemConfigService  # noqa: E402
from app.infrastructure.database.resource_manager import (
    db_resource_manager,  # noqa: E402
)
from app.infrastructure.voice.volc_asr import VolcAsrClient  # noqa: E402

SAMPLE_RATE = 16000
BLOCK = 3200  # 100ms @16k


async def main() -> None:
    # 初始化 DB 引擎，让 SystemConfigService 能读到已配置的火山凭证
    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    app_id = os.environ.get("VOLC_APP_ID") or SystemConfigService.get_value(
        "SEEDUPLEX_APP_ID"
    )
    access_key = os.environ.get("VOLC_ACCESS_KEY") or SystemConfigService.get_value(
        "SEEDUPLEX_ACCESS_KEY"
    )
    if not app_id or not access_key:
        print("❌ 缺火山凭证：VOLC_APP_ID / VOLC_ACCESS_KEY（Access Token）")
        return

    # 检查输入设备
    try:
        sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 无法打开麦克风输入: {exc}")
        print("   检查：系统设置 → 隐私与安全性 → 麦克风，给本终端授权；或插入 USB 麦克风/耳机")
        return

    client = VolcAsrClient(app_id, access_key)
    await client.connect()
    print("已连接 bigmodel_async，开始录音（Ctrl-C 停止）")
    print("提示：正常说话看 451；播放音频(模拟TTS)时再说话，看是否出现 450")

    event_count: dict[int, int] = defaultdict(int)
    stop = asyncio.Event()
    audio_q: asyncio.Queue[bytes] = asyncio.Queue()

    def mic_cb(indata, frames, time_info, status) -> None:  # noqa: ARG001
        audio_q.put_nowait(indata.tobytes())

    async def send_loop() -> None:
        while not stop.is_set():
            try:
                chunk = await asyncio.wait_for(audio_q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await client.send_audio(chunk)
            except Exception as exc:  # noqa: BLE001
                print(f"[send] 异常: {exc}")
                break

    async def recv_loop() -> None:
        while not stop.is_set():
            try:
                r = await asyncio.wait_for(client.receive_response(), timeout=6)
            except asyncio.TimeoutError:
                print("[recv] 6s 无数据（静音中）")
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"[recv] 异常: {exc}")
                break
            ev = r.get("event")
            txt = (r.get("payload_msg") or {}).get("extra", {}).get("origin_text", "")
            event_count[ev] += 1
            flag = "  ← 打断?" if ev == 450 else ""
            print(f"  [ASR] event={ev}  text={txt!r}{flag}")

    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16",
        blocksize=BLOCK, callback=mic_cb,
    )
    try:
        stream.start()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 启动录音失败: {exc}")
        return

    send_task = asyncio.create_task(send_loop())
    recv_task = asyncio.create_task(recv_loop())
    try:
        await stop.wait()
    except KeyboardInterrupt:
        pass

    await client.finish()
    stop.set()
    await asyncio.sleep(2)
    stream.stop()
    await client.close()

    print("\n=== event 统计 ===")
    for ev in sorted(event_count):
        print(f"  event {ev}: {event_count[ev]} 次")
    if 450 in event_count:
        print("\n✅ 收到 event 450 (barge-in) —— 打断事件确认存在")
    else:
        print("\n⚠️ 未收到 event 450 —— 需在播放音频(模拟TTS)时对着麦克风说话再试；若无，打断判定应依赖本地 VAD")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
