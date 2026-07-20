"""Layer-2 smoke: drive a real agent run through the voice WS and wait for done.

Sends one `voice.route` that falls through to `delegate` (empty route index on a
fresh install) and waits for the terminal `voice.route_result(done|failed)` that
`executor` -> `dispatch_agent_run` -> `run_agent_background` -> `finish` pushes
back (design §16). This exercises the REAL Agent loop against the configured
global LLM (Kimi) and verifies end-to-end pushback, so it incurs real API cost
and may take up to ~90s. Not part of the fast protocol harness.

Exit codes: 0 done, 1 failed, 2 timeout, 77 backend not reachable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid

try:
    import websockets
except ImportError:  # pragma: no cover
    print("SKIP: `websockets` not installed")
    sys.exit(77)


def envelope(mtype: str, body: dict, message_id: str | None = None) -> str:
    return json.dumps(
        {
            "version": "2.0",
            "type": mtype,
            "message_id": message_id or str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "body": body,
        }
    )


async def _recv(ws, timeout: float) -> dict:
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def main_async(url: str, text: str, timeout: float) -> int:
    thread_id = str(uuid.uuid4())
    try:
        async with websockets.connect(url) as ws:
            await _recv(ws, 6.0)  # system.init
            await ws.send(envelope("voice.route", {"text": text, "thread_id": thread_id}))
            deadline = time.monotonic() + timeout
            routed = None
            while time.monotonic() < deadline:
                try:
                    frame = await _recv(ws, max(1.0, deadline - time.monotonic()))
                except asyncio.TimeoutError:
                    break
                body = frame.get("body", {})
                if frame.get("type") != "voice.route_result" or body.get("thread_id") != thread_id:
                    continue
                status = body.get("status")
                if status == "routed":
                    routed = body.get("target", {}).get("type")
                    print(f"routed: target={routed!r}")
                    continue
                if status in ("done", "failed"):
                    print(f"{status}: summary={body.get('summary', '')[:200]!r}")
                    return 0 if status == "done" else 1
            print(f"timeout: routed={routed!r}, no terminal done/failed within {timeout}s")
            return 2
    except (OSError, ConnectionRefusedError) as exc:
        print(f"SKIP: backend not reachable at {url} ({exc})")
        return 77


def main() -> int:
    parser = argparse.ArgumentParser(description="Layer-2 agent smoke (real LLM, real pushback).")
    parser.add_argument("--url", default="ws://127.0.0.1:8123/api/v1/voice/ws")
    parser.add_argument(
        "--text",
        default="用中文简短回答：1+1 等于几？只回答结果。",
        help="utterance to route (default: a trivial arithmetic that delegates to agent)",
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    print(f"agent smoke → {args.url} (timeout={args.timeout}s)")
    return asyncio.run(main_async(args.url, args.text, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
