"""Media reference helpers shared by AI message persistence paths.

image/video 工具生成媒体时经 ``stash_media_ref`` 写入
``ctx.metadata.pending_media_refs``；落库前取出合并进 AI 消息的
references，返回后清空 stash，保证引用只消费一次、不跨轮重复。
"""

from __future__ import annotations

from typing import Any


def consume_pending_media_refs(ctx: Any) -> list[dict]:
    """取出并清空执行上下文中暂存的生成媒体引用（stash → 一次性消费）。"""
    refs = list(getattr(ctx.metadata, "pending_media_refs", None) or [])
    if refs:
        ctx.metadata.pending_media_refs = []
    return refs
