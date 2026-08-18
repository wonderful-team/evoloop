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

from app.infrastructure.llm.thinking_adapter import is_reasoning_model

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

                model_name = body.get("model", "")
                # DeepSeek gateway 通道可能在 URL 中携带 deepseek/thinking 标识，
                # 而 body 的 model 可能为空（默认路由）；此处同时校验模型名与 URL。
                is_deepseek = (
                    "deepseek" in url_str.lower()
                    or "thinking" in url_str.lower()
                    or is_reasoning_model(model_name)
                )

                if "messages" in body:
                    # If any assistant message already carries native reasoning_content,
                    # this is a reasoning-model conversation and the provider expects every
                    # assistant message to have reasoning_content passed back. Fill missing
                    # entries from visible content (e.g., synthetic orphaned-tool placeholders)
                    # instead of fabricating a meaningless placeholder.
                    assistant_msgs = [
                        msg
                        for msg in body["messages"]
                        if msg.get("role") == "assistant"
                    ]
                    conversation_has_reasoning = any(
                        msg.get("reasoning_content") for msg in assistant_msgs
                    )
                    reasoning_required = is_deepseek or conversation_has_reasoning

                    modified = False
                    for i, msg in enumerate(body["messages"]):
                        role = msg.get("role")

                        if role == "assistant":
                            if reasoning_required:
                                val = msg.get("reasoning_content")
                                content = msg.get("content")
                                if not val and content:
                                    val = content
                                    logger.debug(
                                        "[ReasoningPatch] Falling back to visible content as "
                                        f"reasoning_content for assistant message #{i}"
                                    )
                                if not val:
                                    continue

                                new_msg = {
                                    "role": "assistant",
                                    "reasoning_content": val,
                                }
                                for k, v in msg.items():
                                    if k in ["role", "reasoning_content"]:
                                        continue
                                    # When we fell back to content-as-reasoning, avoid
                                    # duplicating it as visible content.
                                    if k == "content" and not msg.get("reasoning_content"):
                                        new_msg[k] = ""
                                        continue
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
                logger.debug("[ReasoningPatch] Failed to rewrite request body", exc_info=True)

        return await _original_httpx_send(self, request, **kwargs)

    httpx.AsyncClient.send = _patched_httpx_send  # type: ignore[method-assign]

    logger.info("[Reasoning] Applied reasoning_content safety patches")


# Auto-apply on module import
_apply_reasoning_patch()
