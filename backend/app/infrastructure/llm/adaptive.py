import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI

from app.i18n.service import i18n

logger = logging.getLogger(__name__)


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
        Override _agenerate to implement the retry loop.
        Note: We override _agenerate because it's the core method called by ainvoke/invoke.
        """

        # 0. Initial Configuration
        original_max_tokens = self.max_tokens or self.retry_max_tokens_base
        original_temp = self.temperature

        current_max_tokens = original_max_tokens
        current_temp = original_temp

        for attempt in range(self.adaptive_retries + 1):
            try:
                # Update params for this attempt
                request_kwargs = kwargs.copy()
                request_kwargs["max_tokens"] = current_max_tokens
                request_kwargs["temperature"] = current_temp

                if attempt > 0:
                    logger.info(f"🔄 Adaptive Retry {attempt}/{self.adaptive_retries}: max_tokens={current_max_tokens}, temp={current_temp}")

                # Call Parent Logic
                return await super()._agenerate(messages, stop, run_manager, **request_kwargs)

            except Exception as e:
                error_str = str(e).lower()

                is_context_error = (
                    "context_length_exceeded" in error_str
                    or "maximum context length" in error_str
                    or "prompt is too long" in error_str
                    or "string too long" in error_str
                    or "rate limit" in error_str
                )

                if not is_context_error:
                    raise e

                if attempt == self.adaptive_retries:
                    logger.error(f"❌ Adaptive Retry Exhaused. Final Error: {e}")
                    raise e

                decay_factor = 1.0
                if attempt == 0:
                    decay_factor = 0.9
                elif attempt == 1:
                    decay_factor = 0.8
                else:
                    decay_factor = 0.6

                current_max_tokens = int(current_max_tokens * decay_factor)
                current_temp = max(current_temp - 0.15, 0.05)

                logger.warning(f"⚠️ LLM Context Error detected. Adjusting params: factor={decay_factor}, new_max={current_max_tokens}")

    async def summarize(self, text: str) -> str:
        """
        Generate a concise summary of the input text.
        """
        from langchain_core.prompts import PromptTemplate
        from langchain_core.runnables import (
            RunnableLambda,
            RunnablePassthrough,
        )

        prompt = PromptTemplate.from_template(i18n.get("prompts.adaptive_llm.summarize_prompt"))
        chain = (
            RunnablePassthrough.assign(prompt=prompt)
            | RunnableLambda(lambda x: x["prompt"].format(input=x["input"]))
            | self
        )
        result = await chain.ainvoke({"input": text})
        return result.content
