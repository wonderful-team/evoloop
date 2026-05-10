#!/usr/bin/env python3
"""
Test: Is Gateway doing REAL streaming or buffering?
Measures inter-chunk arrival times to verify true streaming.
"""
import asyncio
import json
import time

import httpx

GATEWAY_URL = "https://evoloop.develop-assistant.cn/gateway/v1"
DIRECT_URL = "https://api.kimi.com/coding/v1"
MODEL = "kimi-k2-thinking-turbo"
API_KEY = "sk-kimi-kDoeERDQ6e6SdZmkDu5S1idimw7rGu8Bo6SOl3PA8RM1yKyJQOhsFtPbZX6BnhMf"


async def measure_stream_latency(url: str, headers: dict, label: str):
    """Measure inter-chunk arrival times."""
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"URL: {url}")
    print(f"{'='*60}")

    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "1+1=? 请详细推理"}],
        "stream": True,
        "enable_thinking": True,
        "return_reasoning": True,
    }

    chunks = []
    start_time = time.time()
    first_chunk_time = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code != 200:
                print(f"Error: {resp.status_code} {await resp.aread()}")
                return None

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        now = time.time()
                        if first_chunk_time is None:
                            first_chunk_time = now
                        chunks.append({
                            "t": now - start_time,
                            "since_first": now - first_chunk_time if first_chunk_time else 0,
                        })

    total_time = time.time() - start_time

    if len(chunks) < 2:
        print("Not enough chunks to measure")
        return None

    # Calculate inter-chunk intervals
    intervals = [chunks[i]["since_first"] - chunks[i-1]["since_first"] for i in range(1, len(chunks))]

    print(f"Total chunks: {len(chunks)}")
    print(f"Total time: {total_time:.3f}s")
    print(f"Time to first chunk (TTFB): {first_chunk_time - start_time:.3f}s")
    print(f"Avg inter-chunk interval: {sum(intervals)/len(intervals)*1000:.1f}ms")
    print(f"Min interval: {min(intervals)*1000:.1f}ms")
    print(f"Max interval: {max(intervals)*1000:.1f}ms")
    print(f"Median interval: {sorted(intervals)[len(intervals)//2]*1000:.1f}ms")

    # Distribution of intervals
    buckets = {
        "<1ms": 0,
        "1-5ms": 0,
        "5-20ms": 0,
        "20-50ms": 0,
        "50-100ms": 0,
        ">100ms": 0,
    }
    for iv in intervals:
        ms = iv * 1000
        if ms < 1:
            buckets["<1ms"] += 1
        elif ms < 5:
            buckets["1-5ms"] += 1
        elif ms < 20:
            buckets["5-20ms"] += 1
        elif ms < 50:
            buckets["20-50ms"] += 1
        elif ms < 100:
            buckets["50-100ms"] += 1
        else:
            buckets[">100ms"] += 1

    print(f"\nInterval distribution:")
    for k, v in buckets.items():
        pct = v / len(intervals) * 100
        bar = "█" * int(pct / 2)
        print(f"  {k:>8}: {v:>4} ({pct:>5.1f}%) {bar}")

    # Check for burst pattern (indicative of buffering)
    # If >80% of chunks arrive within <5ms, likely buffered
    burst_ratio = (buckets["<1ms"] + buckets["1-5ms"]) / len(intervals)
    print(f"\nBurst ratio (<5ms): {burst_ratio*100:.1f}%")
    if burst_ratio > 0.8:
        print("⚠️  HIGH burst ratio - likely BUFFERED streaming")
    else:
        print("✅ Low burst ratio - likely TRUE streaming")

    # Show first 20 intervals
    print(f"\nFirst 20 intervals (ms): {[round(iv*1000, 1) for iv in intervals[:20]]}")

    return {
        "chunks": len(chunks),
        "total_time": total_time,
        "ttfb": first_chunk_time - start_time,
        "avg_interval_ms": sum(intervals)/len(intervals)*1000,
        "burst_ratio": burst_ratio,
    }


async def main():
    direct = await measure_stream_latency(
        f"{DIRECT_URL}/chat/completions",
        {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "KimiCLI/1.5",
        },
        "Direct kimi API"
    )

    gateway = await measure_stream_latency(
        f"{GATEWAY_URL}/chat/completions",
        {
            "Authorization": "Bearer test-token",
            "Content-Type": "application/json",
        },
        "Via Gateway"
    )

    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    if direct and gateway:
        print(f"{'':20} {'Direct':>12} {'Gateway':>12}")
        print(f"{'Chunks':20} {direct['chunks']:>12} {gateway['chunks']:>12}")
        print(f"{'Total time (s)':20} {direct['total_time']:>12.3f} {gateway['total_time']:>12.3f}")
        print(f"{'TTFB (s)':20} {direct['ttfb']:>12.3f} {gateway['ttfb']:>12.3f}")
        print(f"{'Avg interval (ms)':20} {direct['avg_interval_ms']:>12.1f} {gateway['avg_interval_ms']:>12.1f}")
        print(f"{'Burst ratio':20} {direct['burst_ratio']*100:>11.1f}% {gateway['burst_ratio']*100:>11.1f}%")

        if gateway['burst_ratio'] > 0.8:
            print("\n⚠️  Gateway appears to BUFFER chunks before sending")
        else:
            print("\n✅ Gateway appears to do TRUE streaming")


if __name__ == "__main__":
    asyncio.run(main())
