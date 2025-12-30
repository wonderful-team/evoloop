
import asyncio
from typing import List, Dict, Any
import numpy as np
from langchain_core.tools import BaseTool

from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder
from app.logging import logger

class ToolRetriever:
    """
    Manages semantic retrieval of tools to avoid context window saturation.
    Uses in-memory vector storage for ephemeral tool instances.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRetriever, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.embedder = OpenAIEmbedder()
        self.tools: List[BaseTool] = []
        self.embeddings: List[List[float]] = []
        self._indexed_names = set()
        self._lock = asyncio.Lock()

    async def index_tools(self, tools: List[BaseTool]):
        """
        Index a list of tools. Idempotent based on tool name.
        """
        async with self._lock:
            new_tools = []
            texts_to_embed = []
            
            for tool in tools:
                if tool.name in self._indexed_names:
                    continue
                
                self._indexed_names.add(tool.name)
                new_tools.append(tool)
                # Create semantic signature: Name + Description + Args
                # Args schema might be complex, just name+desc is usually best for "intent"
                signature = f"Tool: {tool.name}\nDescription: {tool.description}"
                texts_to_embed.append(signature)
            
            if not new_tools:
                return

            try:
                # Batch embed
                logger.info(f"Embedding {len(new_tools)} new tools for retrieval...")
                vectors = await self.embedder.embed_documents(texts_to_embed)
                
                self.tools.extend(new_tools)
                self.embeddings.extend(vectors)
                logger.info(f"Tool Retrieval Index Updated. Total Tools: {len(self.tools)}")
            except Exception as e:
                logger.error(f"Failed to embed tools: {e}")
                # Remove from set so we retry later?
                for t in new_tools:
                    self._indexed_names.discard(t.name)

    async def retrieve(self, query: str, k: int = 10) -> List[BaseTool]:
        """
        Get top-k relevant tools for the query.
        """
        if not self.tools:
            return []

        try:
            query_vector = await self.embedder.embed_query(query)
            
            # Compute Cosine Similarity
            # Assuming vectors are lists, convert to numpy for speed
            # Cache numpy array if perf needed, but for <1000 items, on-the-fly is fine.
            
            tool_vecs = np.array(self.embeddings)
            q_vec = np.array(query_vector)
            
            # Normalize just in case
            norm_tools = np.linalg.norm(tool_vecs, axis=1)
            norm_q = np.linalg.norm(q_vec)
            
            if norm_q == 0:
                return []

            # (A . B) / (|A|*|B|)
            scores = np.dot(tool_vecs, q_vec) / (norm_tools * norm_q)
            
            # Get Top K indices
            # argsort returns lowest to highest, so we take tail and reverse
            top_indices = np.argsort(scores)[-k:][::-1]
            
            results = []
            for idx in top_indices:
                score = scores[idx]
                tool = self.tools[idx]
                if score > 0.3: # Minimum relevance threshold?
                     results.append(tool)
            
            return results

        except Exception as e:
            logger.error(f"Tool retrieval error: {e}")
            # Fallback: Return all if few, or none?
            # Better to return empty list so Core tools still work
            return []

# Global Instance
tool_retriever = ToolRetriever()
