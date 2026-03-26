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
        Override _agenerate to implement the adaptive retry loop.
        Note: We override _agenerate because it's the core method called by ainvoke/invoke.
        """
        # --- 0. Pre-processing: Repair history for compatibility ---
        from app.core.engine import repair_message_history
        messages = repair_message_history(messages)

        # --- 1. Initial Configuration ---
        # Ensure we have a starting point for current tokens and temperature
        current_max_tokens = self.max_tokens or self.retry_max_tokens_base
        current_temp = self.temperature if self.temperature is not None else 0.7

        for attempt in range(self.adaptive_retries + 1):
            # --- Log Messages for Debugging ---
            try:
                from app.core.engine.message_utils import log_messages
                log_messages(messages, f"AdaptiveChatOpenAI Attempt {attempt}")
            except Exception as e:
                logger.debug(f"Failed to log messages: {e}")

            try:
                # Update params for this specific attempt
                request_kwargs = kwargs.copy()
                request_kwargs["max_tokens"] = current_max_tokens
                request_kwargs["temperature"] = current_temp

                if attempt > 0:
                    logger.info(
                        f"🔄 Adaptive Retry {attempt}/{self.adaptive_retries}: "
                        f"max_tokens={current_max_tokens}, temp={current_temp:.2f}"
                    )

                # Call Parent Logic (ChatOpenAI._agenerate)
                return await super()._agenerate(messages, stop, run_manager, **request_kwargs)

            except Exception as e:
                error_str = str(e).lower()

                # Detect Context Window or common Resource errors
                # These are the errors where 'shrinking' the output might help.
                is_context_error = any(kw in error_str for kw in [
                    "context_length_exceeded", 
                    "maximum context length", 
                    "prompt is too long", 
                    "string too long",
                    "rate limit",
                    "too many tokens"
                ])

                if not is_context_error:
                    # For other errors (Auth, Network, etc.), we don't adapt, just re-raise
                    raise e

                if attempt == self.adaptive_retries:
                    logger.error(f"❌ Adaptive Retry Exhausted. Final Error: {e}")
                    raise e

                # --- 2. Adaptive Logic: Decay Parameters ---
                # Strategy: Reduce output space to make room for input, 
                # and decrease temperature for more deterministic/stable output.
                decay_factor = 1.0
                if attempt == 0:
                    decay_factor = 0.8  # First drop is significant
                elif attempt == 1:
                    decay_factor = 0.6  # Second drop more aggressive
                else:
                    decay_factor = 0.5  # Final attempt half of initial

                current_max_tokens = int(current_max_tokens * decay_factor)
                current_temp = max(current_temp - 0.2, 0.0) # Reduce temp jitter

                logger.warning(
                    f"⚠️ LLM Context Error detected. Adjusting params: "
                    f"factor={decay_factor}, new_max={current_max_tokens}, new_temp={current_temp:.2f}"
                )

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
