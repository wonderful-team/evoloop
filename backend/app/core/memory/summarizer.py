import logging

from app.core.llm.factory import LLMFactory
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


class MemorySummarizer:
    async def summarize(self, text: str) -> str:
        try:
            llm = LLMFactory.create_llm()
            # 生成摘要
            summary = await llm.summarize(text)
            return summary
        except Exception as e:
            # 处理异常
            logger.error(f"Error during summarization: {e}")
            return i18n.get("prompts.memory.summarizer_error")
