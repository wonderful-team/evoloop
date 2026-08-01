"""
reasoning_patch.py — httpx monkey-patch for reasoning_content support.

职责边界：
  - 此模块只做 HTTP 层的兼容补丁，不包含任何业务逻辑
  - 必须在任何 LLM 实例创建之前 import（由 factory.py 保证）
  - 原有的 SDK 补丁已在迁移后移除，
    reasoning_content 的提取现由 AdaptiveChatOpenAI.astream 原生处理
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _apply_reasoning_patch() -> None:
    """Apply httpx monkey-patch for reasoning_content request-body rewriting."""

    _original_httpx_send = httpx.AsyncClient.send

    async def _patched_httpx_send(self: Any, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        url_str = str(request.url)
        if request.method == "POST" and ("/chat/completions" in url_str or "/messages" in url_str):
            try:
                content = request.read()
                body = json.loads(content)

                is_kimi = "kimi" in url_str.lower() or "moonshot" in url_str.lower()
                model_name = body.get("model", "").lower()
                is_deepseek = "deepseek" in url_str.lower() or "thinking" in url_str.lower() or "deepseek" in model_name

                if "messages" in body:
                    modified = False
                    for i, msg in enumerate(body["messages"]):
                        role = msg.get("role")

                        if role == "assistant":
                            if is_kimi or is_deepseek:
                                val = msg.get("reasoning_content")

                                if not val:
                                    val = " " if is_kimi else "...."

                                new_msg = {"role": "assistant", "reasoning_content": val}
                                for k, v in msg.items():
                                    if k not in ["role", "reasoning_content"]:
                                        new_msg[k] = v

                                body["messages"][i] = new_msg
                                modified = True
                            else:
                                if "reasoning_content" in msg:
                                    msg.pop("reasoning_content")
                                    modified = True
                        else:
                            if "reasoning_content" in msg:
                                msg.pop("reasoning_content")
                                modified = True

                    if modified:
                        new_content = json.dumps(body).encode("utf-8")
                        request._content = new_content
                        request.stream = httpx.ByteStream(new_content)
                        request.headers["Content-Length"] = str(len(new_content))
                        if "Transfer-Encoding" in request.headers:
                            del request.headers["Transfer-Encoding"]
            except Exception:
                pass

        return await _original_httpx_send(self, request, **kwargs)

    httpx.AsyncClient.send = _patched_httpx_send  # type: ignore[method-assign]

    logger.info("[Reasoning] Applied Kimi reasoning_content safety patches")


# Auto-apply on module import
_apply_reasoning_patch()
