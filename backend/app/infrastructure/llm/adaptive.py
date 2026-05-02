import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI

from app.i18n.service import i18n
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class AdaptiveRetryState(DynamicBaseModel):
    """Encapsulates the state and logic for an adaptive retry attempt."""
    attempt: int = 0
    max_retries: int = 3
    current_max_tokens: int
    current_temperature: float
    
    def next_state(self) -> "AdaptiveRetryState":
        """Calculates the next state with decayed parameters."""
        decay = 0.8 if self.attempt == 0 else (0.6 if self.attempt == 1 else 0.5)
        return AdaptiveRetryState(
            attempt=self.attempt + 1,
            max_retries=self.max_retries,
            current_max_tokens=int(self.current_max_tokens * decay),
            current_temperature=max(self.current_temperature - 0.2, 0.0)
        )
    
    @property
    def can_retry(self) -> bool:
        return self.attempt < self.max_retries


class AdaptiveChatOpenAI(ChatOpenAI):
    """
    A robust ChatOpenAI wrapper that implements DeepCode's 'Adaptive Token Strategy'.

    Features:
    - Automatically catches 'Context Window Exceeded' errors.
    - Retries with reduced 'max_tokens' (Output) to make room for Input.
    - Lowers 'temperature' on retries for stability.
    """

    retry_max_tokens_base: int = 4096  # Default fallback if not set
    adaptive_retries: int = 3

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Model-driven adaptive generation.
        """
        state = AdaptiveRetryState(
            current_max_tokens=self.max_tokens or self.retry_max_tokens_base,
            current_temperature=self.temperature if self.temperature is not None else 0.7,
            max_retries=self.adaptive_retries
        )

        while True:
            try:
                request_kwargs = {
                    **kwargs,
                    "max_tokens": state.current_max_tokens,
                    "temperature": state.current_temperature
                }

                if state.attempt > 0:
                    logger.info(f"🔄 Adaptive Retry {state.attempt}/{state.max_retries}: {state}")

                return await super()._agenerate(messages, stop, run_manager, **request_kwargs)

            except Exception as e:
                # 只有在可重试且属于 Context 或 Resource 限制时才进行适配
                if state.can_retry and self._is_retryable_error(e):
                    old_state = state
                    state = state.next_state()
                    logger.warning(f"⚠️ Context Error. Adapting: {old_state} -> {state}")
                    continue
                
                raise e

    def _is_retryable_error(self, e: Exception) -> bool:
        """Determines if the error warrants an adaptive retry (token/context limit)."""
        error_str = str(e).lower()
        retryable_keywords = ("context_length_exceeded", "maximum context length", "prompt is too long", "too many tokens")
        return any(kw in error_str for kw in retryable_keywords)

    async def summarize(self, text: str) -> str:
        """
        Generate a concise summary of the input text.
        """
        from langchain_core.prompts import PromptTemplate
        from langchain_core.runnables import (
            RunnableLambda,
            RunnablePassthrough,
        )

        prompt = PromptTemplate.from_template(i18n.get("adaptive_llm.summarize_prompt"))
        chain = (
            RunnablePassthrough.assign(prompt=prompt)
            | RunnableLambda(lambda x: x["prompt"].format(input=x["input"]))
            | self
        )
        result = await chain.ainvoke({"input": text})
        return result.content
