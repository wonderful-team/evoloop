"""
InferenceEngine - Pure LLM execution logic.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from app.core.engine.constants import MAX_STEPS
from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.error_handler import (
    LLM_EXCEPTIONS,
    LLMErrorHandler,
    with_llm_retry,
)
from app.core.engine.message.constants import MessageRole
from app.core.engine.message.native_classes import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.reasoning import (
    extract_reasoning_from_kwargs,
    extract_reasoning_from_message,
)
from app.core.exceptions import InferenceError
from app.infrastructure.llm.factory import LLMConfig, LLMFactory
from app.infrastructure.llm.thinking_adapter import is_reasoning_model
from app.models.schemas.events import MaxStepsReachedEvent
from app.utils.extract import safe_parse_json
from app.utils.redact import redact_secrets

logger = logging.getLogger(__name__)

#: 连续重复的相同工具调用次数阈值，超过即判为 doom loop
DOOM_LOOP_WINDOW = 3


def doom_loop_detected(signatures: list[str], window: int = DOOM_LOOP_WINDOW) -> bool:
    """代码层防循环检测：最近 ``window`` 条工具调用签名完全相同即判循环。

    ``signatures`` 来自 executor 的 ``local_tool_history``（tool_name + 排序参数），
    天然适合识别"重复调同一工具同一参数"的退化行为（§2/§3）。
    """
    if len(signatures) < window:
        return False
    tail = signatures[-window:]
    return len(set(tail)) == 1


class InferenceEngine:
    """Instance-based inference engine for LLM ReAct loops."""

    def __init__(
        self,
        llm_factory: Any | None = None,
        context_trimmer: ContextTrimmer | None = None,
    ):
        self._llm_factory = llm_factory or LLMFactory
        self._context_trimmer = context_trimmer or ContextTrimmer()

    async def create_llm(
        self, model: str | None, temperature: float, streaming: bool = True
    ):
        llm = await self._llm_factory.create_llm(
            model_name=model, temperature=temperature, streaming=streaming
        )
        provider = getattr(llm, "provider", "openai")
        return llm, provider

    def bind_tools(self, llm, tools: list[Any]):
        if tools:
            return llm.bind_tools(tools), {t.name: t for t in tools}
        logger.warning(
            "bind_tools: empty tools list — running bare LLM without tool binding "
            "and empty tool_map; tool execution will be unavailable."
        )
        return llm, {}

    @staticmethod
    @with_llm_retry(max_attempts=3)
    async def _stream_llm_response(llm_with_tools, loop_messages, config):
        response = None
        lc_config = {
            "callbacks": config.get("callbacks"),
            "configurable": config.get("configurable"),
            "metadata": config.get("metadata"),
        }
        accumulated_reasoning: list[str] = []
        async for chunk in llm_with_tools.astream(loop_messages, config=lc_config):
            if response is None:
                response = chunk
            else:
                response = response + chunk

            if chunk.additional_kwargs:
                reasoning = extract_reasoning_from_kwargs(chunk.additional_kwargs)
                if reasoning:
                    accumulated_reasoning.append(reasoning)

        if response is None:
            raise InferenceError(
                error_type="empty_response",
                user_friendly_msg="LLM returned an empty response (no chunks received).",
                raw_error="Empty stream from LLM provider",
            )

        if isinstance(response, AIMessageChunk):
            response = AIMessage(
                content=response.content,
                additional_kwargs=response.additional_kwargs,
                tool_calls=response.tool_calls,
                response_metadata=response.response_metadata,
            )

        # Preserve the full reasoning content in the response so it can be passed back
        # to reasoning-model providers on subsequent turns (e.g. DeepSeek).
        if accumulated_reasoning:
            full_reasoning = "".join(accumulated_reasoning)
            response.additional_kwargs["reasoning_content"] = full_reasoning
            response.additional_kwargs["thinking"] = full_reasoning

        # For reasoning models that emit the thinking process as plain content on
        # tool-call turns, move that content into the reasoning slot so providers
        # receive the correct `reasoning_content` on the next request and the content
        # field does not duplicate the reasoning. Gated on the model being a known
        # reasoning model so ordinary chat models' preambles are not misclassified.
        if (
            response.tool_calls
            and response.content
            and not response.additional_kwargs.get("reasoning_content")
            and not response.additional_kwargs.get("thinking")
            and is_reasoning_model(getattr(llm_with_tools, "model", "") or "")
        ):
            reasoning_from_content = response.content
            response.additional_kwargs["reasoning_content"] = reasoning_from_content
            response.additional_kwargs["thinking"] = reasoning_from_content
            response.content = ""

        return response

    def build_system_messages(self, system_prompt: str) -> list[BaseMessage]:
        # Provider-specific formatting (e.g. Anthropic content-block + cache_control)
        # is applied by the LLM adapter at serialization time, not in the engine.
        return [SystemMessage(content=system_prompt)]

    async def _prepare_turn_context(
        self,
        loop_messages: list[BaseMessage],
        model: str | None,
        name: str,
        thread_id: str | None,
        run_id: str | None,
        config: dict,
    ) -> tuple[list[BaseMessage], dict[str, Any] | None]:
        if model is not None:
            trim_result = self._context_trimmer.trim(
                messages=loop_messages,
                model=model,
                stages={"window", "repair"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
                from app.core.engine.hooks import HookContext, HookEvent, hook_system

                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=thread_id,
                        run_id=run_id,
                        messages=trim_result.messages,
                        project_id=config.get("configurable", {}).get("project_id"),
                        member_id=config.get("configurable", {}).get("member_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    ),
                )

                loop_messages = trim_result.messages
                logger.info(
                    f"[{name}] Loop trim: {trim_result.before_count} -> {trim_result.after_count} msgs"
                )

            if loop_messages:
                for i in range(len(loop_messages) - 1, -1, -1):
                    if loop_messages[i].role == MessageRole.HUMAN:
                        from app.core.engine.context_monitor import ContextMonitor

                        dashboard = (
                            "\n\n"
                            + ContextMonitor.calculate(
                                loop_messages, model=model
                            ).to_prompt()
                        )

                        original_content = loop_messages[i].content
                        if isinstance(original_content, str):
                            new_content = original_content + dashboard
                        elif isinstance(original_content, list):
                            new_content = list(original_content) + [
                                {"type": "text", "text": dashboard.strip()}
                            ]
                        else:
                            break

                        loop_messages[i] = HumanMessage(
                            content=new_content,
                            name=loop_messages[i].name,
                            additional_kwargs=loop_messages[i].additional_kwargs,
                        )
                        break

        msg_count = len(loop_messages)
        if model is not None:
            from app.core.engine.context_monitor import ContextMonitor

            stats = ContextMonitor.calculate(loop_messages, model=model)
            logger.info(
                f"--- {name} Context: {msg_count} msgs, ~{stats.total_tokens} tokens ({stats.usage_ratio * 100:.1f}%) ---"
            )
        else:
            logger.info(f"--- {name} Context: {msg_count} msgs ---")

        return loop_messages, None

    @staticmethod
    def _format_llm_endpoint(llm) -> str:
        return f"model={llm.model or '?'}"

    @staticmethod
    async def _handle_ai_response(
        response: BaseMessage, handler, config_metadata: dict | None = None
    ) -> None:
        if not handler:
            return
        from app.core.engine.message.reasoning import extract_reasoning_from_message

        thinking = extract_reasoning_from_message(response)
        if not response.content and not response.tool_calls and not thinking:
            return
        metadata = {**(config_metadata or {}), **(response.metadata or {})}

        # 关键安全：LLM 可能在回复中回显 {{vault.*}} 注入的密文。
        # 工具输出已由 sensitive_file_censorship_gate 打码，但 AI 文本不受其覆盖，
        # 必须在落库/下发前用 injected_secrets 统一打码。
        from app.core.context.manager import ContextManager

        injected_secrets = ContextManager.current().injected_secrets or []
        content = redact_secrets(response.content or "", injected_secrets)
        thinking = redact_secrets(thinking, injected_secrets) if thinking else thinking

        await handler.handle_ai_message(
            content=content,
            tool_calls=response.tool_calls,
            thinking=thinking,
            metadata=metadata,
        )

    async def _execute_llm_call(
        self,
        llm_with_tools,
        loop_messages: list[BaseMessage],
        config: dict,
        name: str,
        system_prompt: str,
        history_messages: list[BaseMessage],
        turn_id: int,
        on_thinking: Callable | None = None,
        max_steps: int | None = None,
        is_single_shot: bool = False,
        sys_hash: str | None = None,
    ) -> BaseMessage:
        endpoint = self._format_llm_endpoint(llm_with_tools)
        logger.info(f"[{name}] ▶️ LLM call (turn={turn_id}) {endpoint}")

        try:
            start_perf = time.perf_counter()
            response = await self._stream_llm_response(
                llm_with_tools, loop_messages, config
            )
            latency = time.perf_counter() - start_perf
            logger.info(f"[{name}] LLM Latency: {latency:.2f}s")
        except LLM_EXCEPTIONS as e:
            err_str = str(e)
            cfg = config.get("configurable", {})
            lightning_base = cfg.get("lightning_base_url", "")
            # Lightning model context limit — fall back to platform model
            if lightning_base and (
                "n_ctx" in err_str or "context length" in err_str.lower()
            ):
                logger.warning(
                    f"[{name}] Lightning model context limit ({err_str[:100]}), "
                    f"falling back to default model"
                )
                default_model = cfg.get("model", "")
                if default_model:
                    fallback_llm = await self._llm_factory.create_llm(
                        LLMConfig(
                            model_name=default_model, temperature=0.7, streaming=True
                        ),
                    )
                    response = await self._stream_llm_response(
                        fallback_llm, loop_messages, config
                    )
                    latency = time.perf_counter() - start_perf
                    logger.info(f"[{name}] Fallback LLM Latency: {latency:.2f}s")
                else:
                    LLMErrorHandler.raise_inference_error(e)
            else:
                LLMErrorHandler.raise_inference_error(e)

        run_id = config.get("configurable", {}).get("run_id")
        if run_id:
            response.additional_kwargs["run_id"] = run_id

        handler = config.get("configurable", {}).get("message_handler")
        if handler:
            await self._handle_ai_response(
                response, handler, config_metadata=config.get("metadata")
            )
        if handler and handler.last_persisted_message_id:
            response.id = handler.last_persisted_message_id
            response.additional_kwargs["sequence_number"] = (
                handler.last_persisted_sequence
            )

        thinking_content = extract_reasoning_from_message(response)
        if thinking_content:
            logger.info(f"[{name}] Thinking: {thinking_content[:200]}...")
            if on_thinking:
                await on_thinking(thinking_content)

        return response

    async def _process_tool_executions(
        self,
        response: BaseMessage,
        name: str,
        config: dict,
        tool_executor: Any | None,
        local_tool_history: list,
    ) -> list[BaseMessage]:
        tool_results: list[BaseMessage] = []

        tool_calls = response.tool_calls or []
        for tc in tool_calls:
            raw_args = tc.get("args") if isinstance(tc, dict) else None
            if isinstance(raw_args, str):
                tc["args"] = safe_parse_json(raw_args) or {}

        if tool_calls and tool_executor is not None:
            tool_results = await tool_executor.execute_batch(tool_calls, local_tool_history)
            logger.info(f"[{name}] tool_results returned: {len(tool_results)} items")

        return tool_results

    async def run_react_loop(
        self,
        llm_with_tools,
        messages: list[BaseMessage],
        system_prompt: str,
        config: dict,
        name: str,
        max_steps: int = MAX_STEPS,
        tool_executor: Any | None = None,
        on_thinking: Callable | None = None,
        model: str | None = None,
        iteration_count: int | None = None,
        steer_provider: Callable | None = None,
    ) -> dict:
        from app.core.monitoring.activity import activity_monitor

        # Runtime-injected SystemMessage instructions (e.g. a "[SYSTEM NOTE]
        # accept the result and do NOT dispatch another subagent", "[SYSTEM
        # ALERT] previous run truncated/failed") are merged into the static
        # system prompt so they reach the LLM. They were previously dropped by
        # the `role != "system"` filter below, so the LLM never saw the very
        # instructions meant to stop it re-dispatching.
        runtime_system_content = [
            str(m.content)
            for m in messages
            if m.role == "system" and str(getattr(m, "content", "") or "").strip()
        ]
        if runtime_system_content:
            system_prompt = system_prompt + "\n\n" + "\n\n".join(runtime_system_content)
            logger.info(
                f"[{name}] Merged {len(runtime_system_content)} runtime system message(s) "
                f"into system prompt (+{sum(len(c) for c in runtime_system_content)} chars)"
            )
        system_messages = self.build_system_messages(system_prompt)
        history_messages = [m for m in messages if m.role != "system"]
        loop_messages: list[BaseMessage] = system_messages + history_messages

        if not history_messages:
            logger.error(f"[{name}] No history messages! Returning empty.")
            return {
                "messages": [],
                "tool_history": [],
                "last_response": None,
                "is_truncated": False,
            }

        new_messages: list[BaseMessage] = []
        local_tool_history = []
        last_response = None
        steps_used = 0
        _compacted = False

        logger.info(
            f"[{name}] ▶️ run_react_loop START | iteration={iteration_count} | max_steps={max_steps}"
        )

        while steps_used < max_steps:
            logger.info(f"[{name}] 🔄 Step {steps_used + 1}/{max_steps}")
            thread_id = config.get("configurable", {}).get("thread_id")
            run_id = config.get("configurable", {}).get("run_id")
            if thread_id:
                await activity_monitor.check_cancellation(thread_id)

            # §3.5 steer：运行中新消息直接 append 进当前消息流（主循环空闲则走 queue，
            # 由 session 在 delivery 边界处理；此处只在主循环运行中补充相关消息）。
            if steer_provider is not None:
                try:
                    steered = await steer_provider()
                except Exception as e:
                    logger.warning(f"[{name}] steer_provider failed: {e}")
                    steered = []
                if steered:
                    for _m in steered:
                        loop_messages.append(_m)
                    # 对齐 OpenCode「promote any new user input resets provider-turn allowance」
                    steps_used = 0
                    logger.info(
                        f"[{name}] Steered {len(steered)} new message(s) into running loop; budget reset."
                    )

            loop_messages, _ = await self._prepare_turn_context(
                loop_messages=loop_messages,
                model=model,
                name=name,
                thread_id=thread_id,
                run_id=run_id,
                config=config,
            )

            response = await self._execute_llm_call(
                llm_with_tools=llm_with_tools,
                loop_messages=loop_messages,
                config=config,
                name=name,
                system_prompt=system_prompt,
                history_messages=history_messages,
                turn_id=steps_used,
                on_thinking=on_thinking,
                max_steps=max_steps,
            )
            last_response = response

            loop_messages.append(response)
            new_messages.append(response)

            if not response.tool_calls:
                logger.info(f"[{name}] Finished with text response (no tool calls).")
                break

            logger.info(
                f"[{name}] tool_calls detected: {len(response.tool_calls)} calls"
            )

            tool_results = await self._process_tool_executions(
                response=response,
                name=name,
                config=config,
                tool_executor=tool_executor,
                local_tool_history=local_tool_history,
            )

            for tool_msg in tool_results:
                loop_messages.append(tool_msg)
                new_messages.append(tool_msg)

            # 模型感知溢出 → 结构化 compaction（对齐 OpenCode overflow.ts + compaction.ts；
            # 每 run 至多一次，best-effort，失败退化由下一轮 ContextTrimmer 窗口兜底）。
            if not _compacted and model:
                try:
                    from app.core.engine.message.utils import count_total_tokens
                    from app.core.engine.react.compaction import compact_messages
                    from app.core.engine.react.overflow import is_overflow, usable

                    total = count_total_tokens(loop_messages)
                    if is_overflow(total, model):
                        compacted, ok = await compact_messages(
                            loop_messages,
                            model,
                            config,
                            usable_tokens=usable(model),
                        )
                        if ok:
                            loop_messages = compacted
                            _compacted = True
                            logger.info(
                                f"[{name}] Context overflow -> structured compaction applied."
                            )
                except Exception as e:
                    logger.warning(
                        f"[{name}] compaction step failed: {e}", exc_info=True
                    )

            if doom_loop_detected(local_tool_history):
                from app.core.exceptions import DoomLoopException

                raise DoomLoopException(
                    f"[{name}] Detected {DOOM_LOOP_WINDOW} consecutive identical "
                    f"tool invocations ({local_tool_history[-1]}); stopping to avoid infinite loop."
                )

            steps_used += 1

        is_truncated = False
        if last_response and last_response.tool_calls:
            logger.error(f"[{name}] Hit max_steps ({max_steps}) with open tool calls.")
            tools_summary = (
                ", ".join(local_tool_history) if local_tool_history else "None"
            )
            truncation_msg = AIMessage(
                content=(
                    f"[TRUNCATION] Agent reached maximum step limit ({max_steps}) "
                    f"with pending tool calls. Tools executed: {tools_summary}."
                ),
                additional_kwargs={
                    "is_truncated": True,
                    "max_steps": max_steps,
                    "requires_replan": True,
                },
            )
            new_messages.append(truncation_msg)
            is_truncated = True

            # §3 前端感知：命中步数上限时推送 SSE 事件，前端据此在消息列表渲染
            # 一张「已达上限」提示卡片（对齐 QuotaExhaustedEvent 的卡片样式，措辞从简）。
            _thread_id = config.get("configurable", {}).get("thread_id")
            if _thread_id:
                try:
                    publisher = MessagePublisher(_thread_id)
                    await publisher.publish(
                        MaxStepsReachedEvent(
                            thread_id=_thread_id,
                            title="已达本轮的步数上限",
                            message=(
                                f"本轮执行已达到步数上限（{max_steps} 步），"
                                "已在此处暂告一段落。"
                            ),
                            hint="可补充说明或调整指令后继续。",
                        )
                    )
                except Exception as e:
                    logger.warning(
                        f"[{name}] failed to publish max_steps_reached SSE event: {e}",
                        exc_info=True,
                    )

        return {
            "messages": new_messages,
            "tool_history": local_tool_history,
            "last_response": last_response,
            "is_truncated": is_truncated,
        }
