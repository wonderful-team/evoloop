from app.core.llm.factory import LLMFactory

class MemorySummarizer:
    async def summarize(self, text: str) -> str:
        try:
            llm = LLMFactory.create_llm()
            # 生成摘要
            summary = await llm.summarize(text)
            return summary
        except Exception as e:
            # 处理异常
            print(f"Error during summarization: {e}")
            return "无法生成摘要，请稍后重试。"