import logging

from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.infrastructure.llm.factory import LLMFactory, get_default_llm

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
        self.llm = get_default_llm(temperature=0.0)
        self.enabled = settings.ENABLE_QUERY_REWRITING

    async def rewrite(self, query: str) -> str:
        if not self.enabled:
            return query

        # Optimization: Skip rewriting for very short queries or pure code?
        if len(query.split()) < 2 and query.isascii():
            return query

        try:
            from app.utils import render_template
            prompt_text = render_template("planning/query_rewrite.prompt.j2", query=query)

            # Using invoke for simple non-streaming call
            response = await self.llm.ainvoke(prompt_text)
            rewritten = response.content.strip() if hasattr(response, 'content') else str(response).strip()

            # Remove quotes if model added them
            rewritten = rewritten.strip('"').strip("'")

            logger.info(f"QueryRewriter: '{query}' -> '{rewritten}'")
            return rewritten

        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}. Using original query.")
            return query


# Global instance
query_rewriter = QueryRewriter()
