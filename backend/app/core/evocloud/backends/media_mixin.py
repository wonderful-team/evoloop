"""EvoCloud media mixin: chat media upload (chatimg/chatvideo).

AI 生成的图片/视频统一上传到 Member Center 聊天存储，换取公网可访问的 URL。
此后 LLM 看图、图生图参考、桌面/移动端渲染、消息引用均使用该公网 URL。
"""

import logging
import mimetypes
from pathlib import Path

logger = logging.getLogger(__name__)

# 上传端点（MC api 端，checkToken 鉴权；成功码为正数，如 10075=上传成功）
_CHAT_MEDIA_ENDPOINTS = {
    "image": "/api/upload/chatimg",
    "video": "/api/upload/chatvideo",
}


class MediaMixin:
    """Chat media upload endpoints (member center)."""

    async def upload_chat_media(self, file_path: str, kind: str) -> str:
        """Upload a local media file to the member center and return its public URL.

        Args:
            file_path: Local path to the media file.
            kind: "image" or "video".

        Returns:
            Public URL (e.g. https://evoloop.cn/upload/chat_img/...).

        Raises:
            ValueError: unknown kind or upload returned no path.
            RuntimeError: upload failed (business error).
        """
        endpoint = _CHAT_MEDIA_ENDPOINTS.get(kind)
        if not endpoint:
            raise ValueError(f"unknown media kind: {kind}")

        path = Path(file_path)
        if not path.exists():
            raise RuntimeError(f"media file not found: {file_path}")

        import aiofiles

        async with aiofiles.open(path, "rb") as f:
            content = await f.read()

        mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        files = {"file": (path.name, content, mime)}

        resp = await self.request("POST", endpoint, files=files)

        code = resp.get("code", -1)
        if code < 0:
            raise RuntimeError(
                f"media upload failed: code={code}, message={resp.get('message')}"
            )

        data = resp.get("data") or {}
        # chatimg → data.pic_path；chatvideo → data.path
        rel_path = data.get("pic_path") or data.get("path") or ""
        if not rel_path:
            raise RuntimeError(f"media upload returned no path: {resp}")

        public_url = f"{self.root_url.rstrip('/')}/{rel_path.lstrip('/')}"
        logger.info("[EvoCloud] media uploaded: %s → %s (%s bytes)", file_path, public_url, len(content))
        return public_url
