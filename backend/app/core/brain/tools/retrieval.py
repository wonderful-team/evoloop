"""
Active Retrieval Tool for the Supervisor.
Allows the agent to actively search the Brain's long-term memory (Journal + Graph).
"""
import logging
import os
from typing import Optional, Literal

from langchain_core.tools import tool
from app.core.config import settings

logger = logging.getLogger(__name__)

@tool
async def recall_memory(query: str, domain: Literal["journal", "graph", "both"] = "both") -> str:
    """
    Search the agent's long-term memory for information.
    Use this when you need to recall past events, decisions, or specific details that are not in your current context.
    
    Args:
        query: The search text (e.g. "error code for the login bug", "decision on user schema").
        domain: Where to search. 'journal' checks the chronological log. 'graph' checks the Knowledge Graph. 'both' checks both.
    """
    results = []
    
    # 1. Journal Search (Simple Grep for now, can be Vector later)
    if domain in ["journal", "both"]:
        try:
            journal_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "knowledge", "journal.md")
            if os.path.exists(journal_path):
                # Simple exact match line search for speed and simplicity
                # In production, use Vector Store (app.domain.tools.vector_store)
                with open(journal_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    
                matches = [line.strip() for line in lines if query.lower() in line.lower()]
                if matches:
                    results.append(f"### Journal Matches ('{query}')")
                    # Limit to top 5 recent matches
                    for m in matches[-5:]:
                        results.append(f"- {m}")
                else:
                    results.append(f"### Journal: No text matches for '{query}'")
        except Exception as e:
            logger.error(f"Journal search failed: {e}")
            results.append(f"Journal Error: {e}")

    # 2. Graph Search (Concept Entities)
    if domain in ["graph", "both"]:
        try:
            from app.core.memory import memory_manager
            # Re-use existing graph vector/keyword search
            graph_hits = await memory_manager.graph.search(query)
            if graph_hits:
                 results.append(f"\n### Knowledge Graph Matches")
                 results.append(graph_hits)
            else:
                 results.append(f"\n### Knowledge Graph: No matches for '{query}'")
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            
    return "\n".join(results)
