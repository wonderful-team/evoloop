# pyright: reportPrivateImportUsage=false
"""进程内 MockLLM：拦截 SDK 对 litellm 的绑定，做确定性内核测试。

OpenHands v1 SDK 没有内置 MockLLM（0.x 的 mock model provider 已移除）；
SDK 的 LLM 直接调用顶层绑定的 ``litellm.completion`` / ``litellm.acompletion``
（openhands/sdk/llm/llm.py 顶部 from-import）。本模块替换这两个绑定：
- 非流式 → 自造 ``litellm.ModelResponse``
- 流式   → ``list[litellm.ModelResponseStream]``（SDK 自行
  ``stream_chunk_builder`` 聚合并触发 on_token，见 llm.py:_atransport_call）

开关：``EVOLOOP_SDK_LLM_MOCK=1``（由 ``create_llm`` 检测）。
脚本：``EVOLOOP_SDK_LLM_MOCK_SCRIPT`` 指向 JSON 规则表（可选），规则字段：
- ``when_contains``：最后一条 user 消息包含该子串（大小写不敏感）
- ``when_tool_result``：true 表示"最后一条消息是工具结果"时命中
- ``text``：命中后返回的纯文本
- ``reasoning``：可选 thinking 文本（reasoning_content）
- ``tool``：可选 ``{"name": "bash", "arguments": {...}}``，返回工具调用
- ``delay_ms``：可选，命中后 sleep 模拟慢响应

规则 ``tool.arguments`` 的字符串值支持 ``{{task_id}}`` 占位符：替换为消息
文本中的任务 uuid（duty 系统提示词含 "- id: <uuid>"）——规则表是静态
JSON，派发期任务 id 动态变化，占位符让同一份规则服务任意任务。

未命中规则时的内置兜底：
1. 最后一条消息是工具结果 → ``done: <结果摘要>``
2. 文本含 shell 片段（echo/pwd/ls/…）→ bash 工具调用
3. 其他 → echo 最后一条 user 消息
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from functools import lru_cache
from typing import Any

from litellm.types.utils import (
    ChatCompletionDeltaToolCall,
    Choices,
    Delta,
    Function,
    Message,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
    Usage,
)

from app.core.config import _get_env_file_path

logger = logging.getLogger(__name__)

MOCK_MODEL = "openai/mock-llm"
_MOCK_ID_PREFIX = "chatcmpl-mock"
_SHELL_RE = re.compile(r"\b(echo|pwd|ls|cat|sleep|printf|date|whoami)\b[^\n，。；\"']*")
_COMMAND_RE = re.compile(
    r"(?:bash\s*执行|执行命令|执行一下|运行命令|run\s+command)\s*[:：]?\s*([^\n，。；\"']+)"
)

_SEQUENCE_STEP: dict[str, int] = {}
_ORIG: tuple[Any, Any] | None = None
_LOCK = threading.RLock()
_SEQ = 0


def mock_enabled() -> bool:
    if "EVOLOOP_SDK_LLM_MOCK" in os.environ:
        raw = os.environ.get("EVOLOOP_SDK_LLM_MOCK", "").strip()
    else:
        raw = _env_file_values().get("EVOLOOP_SDK_LLM_MOCK", "").strip()
    return raw == "1"


def _script_path() -> str | None:
    if "EVOLOOP_SDK_LLM_MOCK_SCRIPT" in os.environ:
        raw = os.environ.get("EVOLOOP_SDK_LLM_MOCK_SCRIPT", "").strip()
    else:
        raw = _env_file_values().get("EVOLOOP_SDK_LLM_MOCK_SCRIPT", "").strip()
    return raw or None


@lru_cache(maxsize=1)
def _env_file_values() -> dict[str, str]:
    """读 config 的 env 文件：进程环境变量缺失时的兜底。

    后端可能被 `evo`/手动等任意路径重启，进程 env 里不一定带 mock 开关
    （实测被一次无 env 的重启冲掉，E2E 中途掉回真实 LLM 打 403）。
    开关写进 .env 后任何启动方式都生效；进程 env 非空时仍优先。
    """
    values: dict[str, str] = {}
    try:
        with open(_get_env_file_path(), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip("\"'")
    except OSError:
        logger.warning("[MockLLM] env file unreadable", exc_info=True)
    return values


def _load_script() -> list[dict[str, Any]]:
    path = _script_path()
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[MockLLM] script load failed (%s): %s", path, exc)
        return []


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    return ""


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return _text_of(msg.get("content"))
    return ""


def _last_is_tool_result(messages: list[dict[str, Any]]) -> bool:
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        return msg.get("role") == "tool"
    return False


def _last_tool_result(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "tool":
            return _text_of(msg.get("content"))
    return ""


_TASK_ID_PLACEHOLDER = "{{task_id}}"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# duty 系统提示词的任务元信息行（main.duty.task.txt: "- id: <uuid>"）。
# 环境块/技能索引/记忆块可能先于它出现 uuid（设备号、episode id），
# 盲取首个 uuid 会把 update_status 打到不存在的 task 上——优先认这行。
_DUTY_TASK_ID_RE = re.compile(
    r"- id: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)


def _all_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(
        _text_of(msg.get("content")) for msg in messages if isinstance(msg, dict)
    )


def _extract_task_id(messages: list[dict[str, Any]]) -> str | None:
    text = _all_text(messages)
    duty = _DUTY_TASK_ID_RE.search(text)
    if duty:
        return duty.group(1)
    match = _UUID_RE.search(text)
    return match.group(0) if match else None


def _extract_created_ids(messages: list[dict[str, Any]]) -> list[str]:
    """按序提取历史中 tasks create 返回的任务 id（本序列已创建的血统链）。"""
    created: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        text = _text_of(msg.get("content"))
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and payload.get("success") and payload.get("id"):
            created.append(str(payload["id"]))
    return created


def _subst_placeholders(
    args: dict[str, Any], messages: list[dict[str, Any]]
) -> dict[str, Any]:
    """{{task_id}}/{{created_N}}/{{prev_task_id}} 占位符替换。

    - {{task_id}}：当前 duty 任务 id（系统提示词中的 uuid）
    - {{created_N}}：本序列第 N 次 tasks create 返回的 id（N 从 1 起）
    - {{prev_task_id}}：最近一次 create 的 id（= created_last）
    """

    def find_uuid(text: str) -> str | None:
        m = _UUID_RE.search(text)
        return m.group(0) if m else None

    task_id = _extract_task_id(messages)
    created = _extract_created_ids(messages)

    def resolve(value: str) -> str:
        if task_id:
            value = value.replace(_TASK_ID_PLACEHOLDER, task_id)
        for n in range(1, len(created) + 2):
            token = "{{created_" + str(n) + "}}"
            if token in value:
                src = created[n - 1] if n - 1 < len(created) else None
                if src:
                    value = value.replace(token, src)
        if "{{prev_task_id}}" in value and created:
            value = value.replace("{{prev_task_id}}", created[-1])
        return value

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            return resolve(value)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    return walk(args)


def _decide(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """返回 {"text": str} 或 {"tool": {"name":…, "arguments":…}}，可含 reasoning。"""
    user_text = _last_user_text(messages)
    lowered = user_text.lower()
    logger.debug(
        "[MockLLM] decide: roles=%s last_user[:80]=%r",
        [m.get("role") for m in messages if isinstance(m, dict)][-6:],
        user_text[:80],
    )

    for rule in _load_script():
        needle = rule.get("when_contains")
        if needle is not None and needle.lower() not in lowered:
            logger.debug(
                "[MockLLM] skip rule (needle=%r not in last user)",
                needle[:30] if needle else None,
            )
            continue
        if rule.get("when_tool_result") and not _last_is_tool_result(messages):
            continue
        tool_needle = rule.get("when_tool_result_contains")
        if tool_needle is not None and (
            not _last_is_tool_result(messages)
            or tool_needle.lower() not in _last_tool_result(messages).lower()
        ):
            continue
        if rule.get("when_not_tool_result") and _last_is_tool_result(messages):
            continue
        if needle is None and not rule.get("when_tool_result") and tool_needle is None:
            continue
        delay = rule.get("delay_ms")
        if delay:
            time.sleep(float(delay) / 1000.0)
        decision: dict[str, Any] = {}
        if rule.get("reasoning"):
            decision["reasoning"] = str(rule["reasoning"])
        # 序列剧本：一次命中按 (规则, 任务) 计数回放多步——规划任务图谱
        # 等多步编排场景的刚需。
        seq = rule.get("sequence")
        if seq:
            key = f"{needle}:{_extract_task_id(messages) or user_text[:40]}"
            idx = _SEQUENCE_STEP.get(key, 0)
            _SEQUENCE_STEP[key] = idx + 1
            current = seq[min(idx, len(seq) - 1)]
            if current.get("tool"):
                return {
                    "reasoning": current.get("reasoning") or rule.get("reasoning"),
                    "tool": {
                        "name": str(current["tool"].get("name", "bash")),
                        "arguments": _subst_placeholders(
                            current["tool"].get("arguments") or {}, messages
                        ),
                    },
                }
            return {"text": str(current.get("text", "done"))}

        if rule.get("tool"):
            decision["tool"] = {
                "name": str(rule["tool"].get("name", "bash")),
                "arguments": _subst_placeholders(
                    rule["tool"].get("arguments") or {}, messages
                ),
            }
        else:
            decision["text"] = str(rule.get("text", "done"))
        return decision

    if _last_is_tool_result(messages):
        result = _last_tool_result(messages).strip().replace("\n", " ")
        return {"text": f"done: {result[:120]}"}

    command = None
    match = _COMMAND_RE.search(user_text)
    if match:
        command = match.group(1).strip()
    else:
        shell = _SHELL_RE.search(user_text)
        if shell:
            command = shell.group(0).strip()
    if command:
        command = re.sub(r"[\u4e00-\u9fff].*$", "", command).strip()
        return {"tool": {"name": "bash", "arguments": {"command": command}}}

    return {"text": f"mock reply: {user_text[:200]}"}


def _usage_for(messages: list[dict[str, Any]], completion_text: str) -> Usage:
    prompt_chars = sum(
        len(_text_of(m.get("content"))) for m in messages if isinstance(m, dict)
    )
    prompt_tokens = max(1, prompt_chars // 4)
    completion_tokens = max(1, len(completion_text) // 4)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


def _tool_call_payload(decision: dict[str, Any], call_id: str) -> dict[str, Any]:
    tool = decision["tool"]
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": tool["name"],
            "arguments": json.dumps(tool.get("arguments") or {}, ensure_ascii=False),
        },
    }


def _full_response(
    messages: list[dict[str, Any]], decision: dict[str, Any]
) -> ModelResponse:
    global _SEQ
    _SEQ += 1
    text = decision.get("text", "")
    message_kwargs: dict[str, Any] = {"role": "assistant", "content": text or None}
    if decision.get("reasoning"):
        message_kwargs["reasoning_content"] = decision["reasoning"]
    if "tool" in decision:
        message_kwargs["content"] = None
        message_kwargs["tool_calls"] = [
            _tool_call_payload(decision, f"{_MOCK_ID_PREFIX}-call-{_SEQ}")
        ]
    return ModelResponse(
        id=f"{_MOCK_ID_PREFIX}-{_SEQ}",
        choices=[
            Choices(
                index=0,
                message=Message(**message_kwargs),
                finish_reason="tool_calls" if "tool" in decision else "stop",
            )
        ],
        usage=_usage_for(messages, text or "tool"),
        created=int(time.time()),
        model="mock-llm",
    )


def _stream_chunks(
    messages: list[dict[str, Any]], decision: dict[str, Any]
) -> list[ModelResponseStream]:
    global _SEQ
    _SEQ += 1
    response_id = f"{_MOCK_ID_PREFIX}-{_SEQ}"
    chunks: list[ModelResponseStream] = []

    def _chunk(
        delta_kwargs: dict[str, Any],
        finish: str | None = None,
        usage: Usage | None = None,
    ) -> ModelResponseStream:
        return ModelResponseStream(
            id=response_id,
            created=int(time.time()),
            model="mock-llm",
            object="chat.completion.chunk",
            choices=[
                StreamingChoices(
                    index=0,
                    delta=Delta(**delta_kwargs),
                    finish_reason=finish,
                )
            ],
            usage=usage,
        )

    if decision.get("reasoning"):
        chunks.append(_chunk({"reasoning_content": decision["reasoning"]}))
    if "tool" in decision:
        payload = _tool_call_payload(decision, f"{_MOCK_ID_PREFIX}-call-{_SEQ}")
        chunks.append(
            _chunk(
                {
                    "tool_calls": [
                        ChatCompletionDeltaToolCall(
                            index=0,
                            id=payload["id"],
                            type="function",
                            function=Function(
                                name=payload["function"]["name"],
                                arguments=payload["function"]["arguments"],
                            ),
                        )
                    ]
                }
            )
        )
    else:
        text = decision.get("text", "")
        for piece in [text[i : i + 8] for i in range(0, len(text), 8)] or [""]:
            chunks.append(_chunk({"content": piece}))
    chunks.append(
        _chunk(
            {},
            finish="tool_calls" if "tool" in decision else "stop",
            usage=_usage_for(messages, decision.get("text") or "tool"),
        )
    )
    return chunks


def _render(kwargs: dict[str, Any]) -> Any:
    messages = list(kwargs.get("messages") or [])
    joined = json.dumps(messages, ensure_ascii=False)[:4000]
    if "context-aware state summary" in joined or "summar" in joined.lower():
        logger.info(
            "[MockLLM] condensation summarizer call detected (n_messages=%d)",
            len(messages),
        )
    decision = _decide(messages)
    if kwargs.get("stream"):
        return _stream_chunks(messages, decision)
    return _full_response(messages, decision)


def _render_sync(**kwargs: Any) -> Any:
    return _render(kwargs)


async def _render_async(**kwargs: Any) -> Any:
    delay = os.environ.get("EVOLOOP_MOCK_DELAY_MS")
    if delay:
        await asyncio.sleep(float(delay) / 1000.0)
    return _render(kwargs)


def install() -> None:
    """替换 SDK llm.py 顶层绑定的 litellm completion 函数（幂等）。

    ``litellm_acompletion`` 绑定必须是 async 函数——SDK 以
    ``await litellm_acompletion(...)`` 调用；流式结果用普通
    list 即可（SDK _atransport_call 兼容 sync iterable）。
    """
    global _ORIG
    with _LOCK:
        if _ORIG is not None:
            return
        import openhands.sdk.llm.llm as sdk_llm_mod

        _ORIG = (sdk_llm_mod.litellm_completion, sdk_llm_mod.litellm_acompletion)
        sdk_llm_mod.litellm_completion = _render_sync
        sdk_llm_mod.litellm_acompletion = _render_async
        logger.info("[MockLLM] installed (model=%s)", MOCK_MODEL)


def uninstall() -> None:
    global _ORIG
    with _LOCK:
        if _ORIG is None:
            return
        import openhands.sdk.llm.llm as sdk_llm_mod

        sdk_llm_mod.litellm_completion, sdk_llm_mod.litellm_acompletion = _ORIG
        _ORIG = None
        logger.info("[MockLLM] uninstalled")
