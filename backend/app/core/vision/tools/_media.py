"""Shared media helpers for image/video facade tools (generation path)."""

import asyncio
import logging
import os
import tempfile

import httpx

logger = logging.getLogger(__name__)


async def download_bytes(url: str) -> bytes:
    """Download a URL and return its bytes (async)."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def write_temp(data: bytes, suffix: str) -> str:
    """Write bytes to a unique temp file (async-safe) and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="evoloop_media_")

    def _write() -> None:
        with os.fdopen(fd, "wb") as f:
            f.write(data)

    await asyncio.to_thread(_write)
    return path


async def remove_file(path: str) -> None:
    """Best-effort unlink (async-safe)."""

    def _unlink() -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    await asyncio.to_thread(_unlink)


async def load_source_bytes(source: str, config=None) -> bytes:
    """Load reference image bytes from an http(s) URL or a local/uploads path."""
    if source.startswith(("http://", "https://")):
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(source)
            resp.raise_for_status()
            return resp.content

    from app.core.file.tools.utils import resolve_and_validate_path

    resolved = await resolve_and_validate_path(source, config)
    import aiofiles

    async with aiofiles.open(resolved, "rb") as f:
        return await f.read()


def stash_media_ref(media_type: str, target_id: str, target_name: str) -> None:
    """把生成的媒体引用暂存到执行上下文，供 AI 消息持久化时合并为 references。"""
    from app.core.context import ContextManager

    ctx = ContextManager.current()
    pending = list(getattr(ctx.metadata, "pending_media_refs", None) or [])
    pending.append(
        {
            "type": media_type,
            "target_id": target_id,
            "target_name": target_name,
            "meta_data": {"source_path": target_id},
        }
    )
    ctx.metadata.pending_media_refs = pending
