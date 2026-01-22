from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.llm.factory import LLMFactory
import logging
logger = logging.getLogger(__name__)


class QueryRewriter:
    """
    Rewrites user queries to improve retrieval recall, specifically for:
    1. Cross-lingual mapping (Chinese -> English technical terms)
    2. Terminology expansion (e.g., "auth" -> "authentication", "login", "jwt")
    """

    def __init__(self):
        # Use a cheap/fast model for rewriting if possible (e.g. gpt-3.5-turbo or haiku)
        # For now, default to configured GENERAL_AGENT_MODEL
        self.llm = LLMFactory.get_llm(
            provider=settings.EMBEDDING_PROVIDER
            if settings.EMBEDDING_PROVIDER != "local"
            else "openai",  # Fallback logic
            model=settings.GENERAL_AGENT_MODEL,
            temperature=0.0,
        )
        self.enabled = settings.ENABLE_QUERY_REWRITING

    async def rewrite(self, query: str) -> str:
        if not self.enabled:
            return query

        # Optimization: Skip rewriting for very short queries or pure code?
        if len(query.split()) < 2 and query.isascii():
            return query

        try:
            prompt = (
                "You are a query expansion assistant for a code search engine.\n"
                "The user will provide a query (likely in Chinese) about a codebase.\n"
                "Your task is to:\n"
                "1. Translate the query intention to English.\n"
                "2. Extract 3-5 technical keywords/synonyms relevant to the code implementation.\n"
                "3. Output ONLY the rewritten query string combining original and new keywords. Do not explain.\n\n"
                f"Original Query: {query}\n"
                "Rewritten Query:"
            )

            # Using invoke for simple non-streaming call
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            rewritten = response.content.strip()

            # Remove quotes if model added them
            rewritten = rewritten.strip('"').strip("'")

            logger.info(f"QueryRewriter: '{query}' -> '{rewritten}'")
            return rewritten

        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}. Using original query.")
            return query


# Global instance
query_rewriter = QueryRewriter()
