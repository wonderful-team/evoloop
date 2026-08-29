"""Audio sample-format helpers: PCM s16le <-> f32le conversion."""

import struct


def s16le_to_f32le(data: bytes) -> bytes:
    """Convert 16-bit signed little-endian PCM to IEEE float32 little-endian.

    Handles the Volc 'pcm' format (s16le mono) and produces the f32le
    contract expected by the Rust voice client.
    """
    if not data:
        return b""
    count = len(data) // 2
    samples = struct.unpack(f"<{count}h", data)
    return struct.pack(f"<{count}f", *(s / 32768.0 for s in samples))
