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
    """Load reference image bytes from an http(s) URL or a resolved local path."""
    if source.startswith(("http://", "https://")):
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(source)
            resp.raise_for_status()
            return resp.content

    resolved = await resolve_media_source(source, config)
    import aiofiles

    async with aiofiles.open(resolved, "rb") as f:
        return await f.read()


async def resolve_media_source(source: str, config=None) -> str:
    """Resolve a media source to either an http(s) URL or an absolute local path.

    Handles: http(s) URLs (as-is), ``/api/v1/files/raw?path=...`` links,
    ``uploads/...`` relative paths (mapped to CHAT_UPLOAD_DIR), and local
    absolute paths. Raises on unresolvable inputs (Fail-Fast).
    """
    if source.startswith(("http://", "https://")):
        return source

    # /api/v1/files/raw?path=uploads/x.jpg → 内层路径
    if source.startswith("/api/"):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(source).query)
        inner = query.get("path", [None])[0]
        if not inner:
            raise ValueError(f"unresolvable API media path: {source}")
        source = inner

    # uploads/ 命名空间：复用 raw 端点的权威解析（线程隔离 / member 物理根 / legacy）
    if source.lstrip("/").startswith("uploads/"):
        import os

        from app.api.routes.files import _resolve_upload_file
        from app.core.project.utils import current_member_id

        resolved = _resolve_upload_file(source.lstrip("/"), current_member_id() or 0)
        if resolved and os.path.isfile(resolved):
            return resolved
        raise FileNotFoundError(f"upload file not found: {source}")

    # 本地绝对路径：原样返回，存在性由调用方校验（保持 /tmp 帧等既有场景可用）
    import os

    if os.path.isabs(source):
        return source

    from app.core.file.tools.utils import resolve_and_validate_path

    return await resolve_and_validate_path(source, config)


def stash_media_ref(media_type: str, target_id: str, target_name: str) -> None:
    """把生成的媒体引用暂存到执行上下文，供 AI 消息持久化时合并为 references。"""
    from app.core.context import ContextManager
    from app.utils.id import gen_uuid

    ctx = ContextManager.current()
    pending = list(getattr(ctx.metadata, "pending_media_refs", None) or [])
    pending.append(
        {
            "id": gen_uuid(),
            "type": media_type,
            "target_id": target_id,
            "target_name": target_name,
            "meta_data": {"source_path": target_id},
        }
    )
    ctx.metadata.pending_media_refs = pending
