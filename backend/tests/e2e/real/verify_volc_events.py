"""火山流式 ASR 事件号验证脚本。

驱动真实 VolcAsrClient 连接 bigmodel_async，把收到的所有 event 号 + 文本打印出来。
目的：确认火山实际下发哪些事件号 —— 尤其打断事件 450（barge-in）是否真的出现。

用法（在 backend 目录下）：
    uv run python <此脚本> <音频文件.wav|.mp3|...>
    # 建议用一段含停顿的语音；如需验证打断 450，可在识别过程中让第二个人说话。
"""

import asyncio
import os
import subprocess
import sys

BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, BACKEND_DIR)

from app.infrastructure.config.service import SystemConfigService  # noqa: E402
from app.infrastructure.database.resource_manager import (
    db_resource_manager,  # noqa: E402
)
from app.infrastructure.voice.volc_asr import VolcAsrClient  # noqa: E402

CHUNK_BYTES = 3200  # 100ms @ 16k/16bit/mono


def to_pcm_16k(path: str) -> bytes:
    """ffmpeg 转 16k/16bit/mono 裸 PCM。"""
    res = subprocess.run(
        [
            "ffmpeg", "-v", "quiet", "-y", "-i", path,
            "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
            "-f", "s16le", "-",
        ],
        capture_output=True,
    )
    if res.returncode != 0:
        print("ffmpeg 转换失败:", res.stderr.decode()[:500])
        sys.exit(1)
    return res.stdout


async def main() -> None:
    if len(sys.argv) < 2:
        print("用法: uv run python verify_volc_events.py <音频文件>")
        return

    # 初始化 DB 引擎，让 SystemConfigService 能读到已配置的火山凭证
    await db_resource_manager.initialize(create_tables=False, seed_data=False)

    # 优先环境变量（不落库），fallback 到 SystemConfigService
    app_id = os.environ.get("VOLC_APP_ID") or SystemConfigService.get_value(
        "SEEDUPLEX_APP_ID"
    )
    access_key = os.environ.get("VOLC_ACCESS_KEY") or SystemConfigService.get_value(
        "SEEDUPLEX_ACCESS_KEY"
    )
    if not app_id or not access_key:
        print("❌ 未配置火山凭证：用环境变量 VOLC_APP_ID / VOLC_ACCESS_KEY 传入，或在 SystemConfig 配置")
        return

    pcm = to_pcm_16k(sys.argv[1])
    print(f"音频: {len(pcm)} bytes (~{len(pcm) / 32000:.1f}s @16k)")

    client = VolcAsrClient(app_id, access_key)
    await client.connect()
    print("已连接 bigmodel_async")

    event_count: dict[int, int] = {}
    event_text: dict[int, list[str]] = {}

    async def recv_loop() -> None:
        while True:
            try:
                r = await asyncio.wait_for(client.receive_response(), timeout=6)
            except asyncio.TimeoutError:
                print("[recv] 超时，假设无更多数据")
                break
            except Exception as exc:  # noqa: BLE001
                print(f"[recv] 异常: {exc}")
                break
            ev = r.get("event")
            txt = (
                (r.get("payload_msg") or {}).get("extra", {}).get("origin_text", "")
            )
            event_count[ev] = event_count.get(ev, 0) + 1
            event_text.setdefault(ev, [])
            if txt:
                event_text[ev].append(txt)
            print(f"  [ASR] event={ev}  text={txt!r}")
        await client.close()

    rtask = asyncio.create_task(recv_loop())

    # 边发边收（bigmodel_async 双向流式：结果变化才返回）
    for i in range(0, len(pcm), CHUNK_BYTES):
        await client.send_audio(pcm[i : i + CHUNK_BYTES])
        await asyncio.sleep(0.05)

    await client.finish()  # 负包 → 最终结果
    await rtask

    print("\n=== event 统计 ===")
    for ev in sorted(event_count, key=lambda e: (e is None, e)):
        samples = event_text.get(ev, [])[:2]
        print(f"  event {ev}: {event_count[ev]} 次" + (f", 文本样例: {samples}" if samples else ""))

    if 450 in event_count:
        print("\n✅ 收到 event 450 (barge-in) —— 打断事件在真实链路上存在")
    else:
        print("\n⚠️ 未收到 event 450 —— 打断判定依赖的 450 未在本次会话中出现")
        print("   若需确认，请在识别过程中让第二个人说话（模拟打断），观察是否有 event 450")


if __name__ == "__main__":
    asyncio.run(main())
