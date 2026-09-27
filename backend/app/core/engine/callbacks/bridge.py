"""
Callback bridge utilities for connecting native LLM streams to callback handlers.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

# Intentionally wide except — callbacks are third-party pluggable handlers
# that must never break the main LLM flow. Narrower types would risk leaking
# callback bugs into production.
_CALLBACK_EXCEPTIONS = (
    ValueError,
    OSError,
    RuntimeError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    NotImplementedError,
    LookupError,
    IndexError,
)

logger = logging.getLogger(__name__)


def _get_callbacks(config: dict | None) -> list:
    if not config:
        return []
    cbs = config.get("callbacks")
    if not cbs:
        return []
    if isinstance(cbs, list):
        return cbs
    return [cbs]


def _get_run_id(config: dict | None) -> str:
    if config:
        configurable = config.get("configurable") or {}
        rid = configurable.get("run_id")
        if rid and not str(rid).startswith("run-"):
            return str(rid)
    return str(uuid4())


def _get_metadata(config: dict | None) -> dict:
    if not config:
        return {}
    return config.get("metadata") or {}


async def emit_llm_start(
    callbacks: list, run_id: str, metadata: dict | None = None
) -> None:
    for cb in callbacks:
        try:
            await cb.on_llm_start(
                serialized={},
                prompts=[],
                run_id=run_id,
                metadata=metadata or {},
            )
        except _CALLBACK_EXCEPTIONS as e:
            logger.debug(f"[CallbackBridge] on_llm_start failed: {e}", exc_info=True)


async def emit_llm_new_token(
    callbacks: list,
    token: str,
    chunk_msg: Any,
    run_id: str,
) -> None:
    for cb in callbacks:
        try:
            await cb.on_llm_new_token(
                token=token,
                chunk=SimpleNamespace(message=chunk_msg),
                run_id=run_id,
            )
        except _CALLBACK_EXCEPTIONS as e:
            logger.warning(
                f"[CallbackBridge] on_llm_new_token failed: {e}", exc_info=True
            )


async def emit_llm_end(
    callbacks: list,
    final_message: Any,
    run_id: str,
) -> None:
    for cb in callbacks:
        try:
            msg = SimpleNamespace(
                message=final_message,
                text=getattr(final_message, "content", ""),
            )
            result = SimpleNamespace(generations=[[msg]])
            await cb.on_llm_end(response=result, run_id=run_id)
        except _CALLBACK_EXCEPTIONS as e:
            logger.debug(f"[CallbackBridge] on_llm_end failed: {e}", exc_info=True)


async def emit_tool_start(
    callbacks: list,
    tool_name: str,
    tool_input: Any,
    run_id: str,
    parent_run_id: str | None = None,
    tool_call_id: str | None = None,
) -> None:
    for cb in callbacks:
        try:
            await cb.on_tool_start(
                serialized={"name": tool_name},
                input_str=str(tool_input),
                run_id=run_id,
                parent_run_id=parent_run_id,
                tool_call_id=tool_call_id,
            )
        except _CALLBACK_EXCEPTIONS as e:
            logger.info(
                f"[CallbackBridge] on_tool_start failed for {getattr(cb, '__class__', None)}: {e}",
                exc_info=True,
            )


async def emit_tool_end(
    callbacks: list,
    tool_name: str,
    output: str,
    run_id: str,
    parent_run_id: str | None = None,
) -> None:
    for cb in callbacks:
        try:
            await cb.on_tool_end(
                output=output,
                name=tool_name,
                run_id=run_id,
                parent_run_id=parent_run_id,
            )
        except _CALLBACK_EXCEPTIONS as e:
            logger.debug(f"[CallbackBridge] on_tool_end failed: {e}", exc_info=True)


async def emit_tool_error(
    callbacks: list,
    error: Exception,
    run_id: str,
    parent_run_id: str | None = None,
) -> None:
    for cb in callbacks:
        try:
            await cb.on_tool_error(
                error=error,
                run_id=run_id,
                parent_run_id=parent_run_id,
            )
        except _CALLBACK_EXCEPTIONS as e:
            logger.debug(f"[CallbackBridge] on_tool_error failed: {e}", exc_info=True)
