"""
Active Retrieval Tool for the Supervisor.
Allows the agent to actively search the Brain's long-term memory (Journal + Graph).
"""
import os
import json
import logging
from typing import Any, List, Optional, Dict, Literal

from app.core.config import settings
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(is_pollable=True)
async def recall_memory(query: str, domain: str = "both") -> str:
    """
    Search the agent's long-term memory for information.
    Use this when you need to recall past events, decisions, or specific details that are not in your current context.
    
    Args:
        query: The search text (e.g. "error code for the login bug", "decision on user schema").
        domain: Where to search. 'journal' checks the chronological log. 'graph' checks the Knowledge Graph. 'both' checks both.
    """
    result: Dict[str, Any] = {}
    errors: List[str] = []

    # 1. Journal Search (Simple Grep for now, can be Vector later)
    if domain in ["journal", "both"]:
        journal_data: Dict[str, Any] = {"matches": []}
        try:
            journal_path = os.path.join(settings.BRAIN_MEMORY_ROOT, "knowledge", "journal.md")
            if os.path.exists(journal_path):
                # Simple exact match line search for speed and simplicity
                with open(journal_path, encoding="utf-8") as f:
                    lines = f.readlines()

                matches = [line.strip() for line in lines if query.lower() in line.lower()]
                if matches:
                    # Limit to top 5 recent matches
                    journal_data["matches"] = matches[-5:]
                else:
                    journal_data["message"] = f"No text matches for '{query}'."
            else:
                journal_data["message"] = "Journal file not found."
        except Exception as e:
            logger.error(f"Journal search failed: {e}")
            journal_data["error"] = str(e)
            errors.append(f"Journal Error: {e}")
        result["journal"] = journal_data

    # 2. Graph Search (Concept Entities)
    if domain in ["graph", "both"]:
        kg_data: Dict[str, Any] = {"matches": []}
        try:
            from app.core.memory import memory_manager
            # Re-use existing graph vector/keyword search
            graph_hits = await memory_manager.graph.search(query)
            if graph_hits:
                kg_data["matches"] = graph_hits
            else:
                kg_data["message"] = f"No matches for '{query}'."
        except Exception as e:
            logger.error(f"Graph search failed: {e}")

    return "\n".join(results)
