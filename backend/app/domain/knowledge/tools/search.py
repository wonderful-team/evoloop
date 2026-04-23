"""
kb_search - Search documents in the knowledge base using FTS5.
"""

import logging
import re
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg
from pydantic import Field

from app.core.tools import evoloop_tool
from app.domain.knowledge.services.search import get_fts_service
from app.domain.knowledge.services.store import KnowledgeStoreService

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "搜索知识库", "en": "Search Knowledge Base"}
)
async def kb_search(
    pattern: Annotated[str, Field(description="Search pattern (FTS5 syntax: 'phrase' for exact, term1 AND term2, etc.)")],
    path: Annotated[str, Field(default="", description="Subdirectory to search in")] = "",
    collection: Annotated[str, Field(default="", description="Collection to search in")] = "",
    source_project_id: Annotated[int, Field(default=0, description="Workspace project ID to prioritize")] = 0,
    context_lines: Annotated[int, Field(default=2, ge=0, le=10, description="Context lines around matches")] = 2,
    case_sensitive: Annotated[bool, Field(default=False, description="Case sensitive search")] = False,
    max_results: Annotated[int, Field(default=20, ge=1, le=100, description="Maximum results")] = 20,
    use_fts: Annotated[bool, Field(default=True, description="Use full-text search index (faster)")] = True,
    search_mode: Annotated[str, Field(default="fts", description="Search mode: 'fts' (full-text), 'semantic' (vector), 'hybrid' (both) (T-3.3)")] = "fts",
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Search for text patterns in the knowledge base using FTS5, semantic vector search, or hybrid fusion.

    Supports three search modes:
    - "fts": Full-text search (BM25 ranking, fastest, default)
    - "semantic": Vector semantic search (natural language understanding)
    - "hybrid": FTS + vector + citation recommendation fusion (most comprehensive)

    FTS5 query syntax for advanced searching:
    - Simple term: kb_search(pattern="authentication")
    - Exact phrase: kb_search(pattern='"JWT token"')
    - AND/OR: kb_search(pattern="auth AND token"), kb_search(pattern="auth OR oauth")
    - Prefix: kb_search(pattern="auth*")
    - Exclude: kb_search(pattern="auth NOT oauth")

    Examples:
        - Simple search: kb_search(pattern="JWT")
        - Exact phrase: kb_search(pattern='"API key"')
        - Semantic: kb_search(pattern="authentication methods", search_mode="semantic")
        - Hybrid: kb_search(pattern="database", collection="backend", search_mode="hybrid")
        - Regex fallback: kb_search(pattern="def authenticate", use_fts=False)

    Args:
        pattern: Search pattern (FTS5 syntax supported in fts/hybrid modes)
        path: Subdirectory to search in (default: all)
        collection: Collection to search in (default: all collections)
        source_project_id: Workspace project ID to prioritize in results
        context_lines: Lines of context around matches (default: 2)
        case_sensitive: Whether search is case sensitive (default: false)
        max_results: Maximum number of matches to return (default: 20)
        use_fts: Use full-text search index (default: true, faster)
        search_mode: Search strategy — "fts", "semantic", or "hybrid" (T-3.3)

    Returns:
        List of matches with file paths, highlights, relevance scores, and citation-based recommendations.
    """

    try:
        # T-3.3: Route to appropriate search mode
        if search_mode == "semantic":
            return await _semantic_search(pattern, collection, max_results)
        elif search_mode == "hybrid":
            return await _hybrid_search(pattern, collection, max_results, context_lines)
        else:
            # Default FTS mode (backward compatible)
            if use_fts:
                try:
                    fts = get_fts_service()
                    results = await fts.search(
                        query=pattern,
                        collection=collection or None,
                        limit=max_results
                    )

                    if results.total > 0:
                        return _format_fts_results(results, context_lines)

                except Exception as e:
                    logger.warning(f"FTS search failed, falling back to grep: {e}")

            # Fallback to grep-style search
            return await _grep_search(pattern, path, collection, context_lines, case_sensitive, max_results)

    except Exception as e:
        logger.error(f"kb_search failed: {e}")
        return f"Search error: {str(e)}"


async def _semantic_search(query: str, collection: str, max_results: int) -> str:
    """Semantic vector search (T-3.3)."""
    from app.domain.knowledge.services.vector_search import get_kb_vector_service

    try:
        vector_service = get_kb_vector_service()
        results = await vector_service.search(
            query=query,
            collection=collection or None,
            top_k=max_results,
        )

        if not results:
            return f"Semantic search: no vector matches for '{query}'"

        lines = []
        lines.append(f"Semantic Search: '{query}'")
        lines.append(f"   Found {len(results)} matches")
        lines.append("")

        for i, result in enumerate(results, 1):
            lines.append(f"- {result.get('title', 'Untitled')}")
            lines.append(f"   Path: {result['doc_id']} (Score: {result.get('score', 0):.3f})")
            content = result.get('content', '')
            if content:
                snippet = content.replace('\n', ' ')[:300]
                lines.append(f"   {snippet}...")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.warning(f"Semantic search failed: {e}")
        return f"Semantic search error: {e}"


async def _hybrid_search(query: str, collection: str, max_results: int, context_lines: int) -> str:
    """Hybrid search combining FTS, vector, and citation recommendations (T-3.3 + 深化)."""
    from app.domain.knowledge.services.vector_search import get_kb_vector_service
    from app.domain.knowledge.services.citations import get_citation_tracker

    fts_results = []
    vector_results = []

    # FTS search
    try:
        fts = get_fts_service()
        fts_res = await fts.search(
            query=query,
            collection=collection or None,
            limit=max_results,
        )
        fts_results = fts_res.results
    except Exception as e:
        logger.warning(f"Hybrid FTS failed: {e}")

    # Vector search
    try:
        vector_service = get_kb_vector_service()
        vector_results = await vector_service.search(
            query=query,
            collection=collection or None,
            top_k=max_results,
        )
    except Exception as e:
        logger.warning(f"Hybrid vector search failed: {e}")

    # Reciprocal Rank Fusion (RRF)
    k = 60
    scores: dict[str, float] = {}
    doc_info: dict[str, dict] = {}

    for rank, result in enumerate(fts_results, start=1):
        doc_id = result.path
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
        doc_info[doc_id] = {
            "title": result.title,
            "snippet": result.highlights or result.content_snippet,
            "score": result.bm25_score,
            "source": "fts",
        }

    for rank, result in enumerate(vector_results, start=1):
        doc_id = result["doc_id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
        if doc_id not in doc_info:
            doc_info[doc_id] = {
                "title": result.get("title", "Untitled"),
                "snippet": result.get("content", "")[:200],
                "score": result.get("score", 0),
                "source": "vector",
            }
        else:
            doc_info[doc_id]["source"] = "both"

    # Citation boost (引用推荐深化)
    try:
        tracker = get_citation_tracker()
        for doc_id in list(scores.keys()):
            stats = await tracker.get_document_stats(doc_id)
            if stats and stats.total_citations > 0:
                citation_boost = min(stats.total_citations * 0.01, 0.05)
                scores[doc_id] += citation_boost
    except Exception as e:
        logger.debug(f"Citation boost skipped: {e}")

    if not scores:
        return f"Hybrid search: no matches for '{query}'"

    # Re-sort after citation boost
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_results]

    # Co-citation recommendations for top results (引用推荐深化)
    recommendations = []
    try:
        tracker = get_citation_tracker()
        seen = {doc_id for doc_id, _ in ranked}
        for doc_id, _ in ranked[:3]:
            recs = await tracker.get_recommendations(doc_id, limit=3)
            for rec in recs:
                if rec.path not in seen:
                    seen.add(rec.path)
                    recommendations.append(rec)
    except Exception as e:
        logger.debug(f"Recommendation fetch skipped: {e}")

    lines = []
    lines.append(f"Hybrid Search: '{query}'")
    lines.append(f"   Found {len(ranked)} matches (FTS: {len(fts_results)}, Vector: {len(vector_results)})")
    lines.append("")

    for doc_id, rrf_score in ranked:
        info = doc_info[doc_id]
        lines.append(f"- {info['title']}")
        lines.append(f"   Path: {doc_id} (RRF: {rrf_score:.3f}, Source: {info['source']})")
        snippet = info.get("snippet", "")
        if snippet:
            lines.append("   " + snippet.replace('\n', ' ')[:300])
        lines.append("")

    # Append citation recommendations (引用推荐深化)
    if recommendations:
        lines.append("📌 Recommended (often cited together):")
        lines.append("")
        for rec in recommendations[:5]:
            lines.append(f"- {rec.path}")
            lines.append(f"   Reason: {rec.reason} (relevance: {rec.relevance:.2f})")
            lines.append("")

    return "\n".join(lines)


def _format_fts_results(results, context_lines: int) -> str:
    """Format FTS search results."""
    lines = []
    lines.append(f"FTS Search: '{results.query}'")
    lines.append(f"   Found {results.total} matches")
    
    # Facets
    if results.facets.get("collections"):
        collections = ", ".join(f"{p}({c})" for p, c in list(results.facets["collections"].items())[:5])
        lines.append(f"   Projects: {collections}")
    
    lines.append("")
    
    for i, result in enumerate(results.results, 1):
        lines.append(f"- {result.title}")
        lines.append(f"   Path: {result.path} (Score: {result.bm25_score:.2f})")
        
        # Show highlighted snippet
        if result.highlights:
            lines.append("   " + result.highlights.replace('\n', ' '))
        
        lines.append("")
    
    if results.total > len(results.results):
        lines.append(f"... and {results.total - len(results.results)} more results")
    
    return "\n".join(lines)


async def _grep_search(
    pattern: str,
    path: str,
    collection: str,
    context_lines: int,
    case_sensitive: bool,
    max_results: int
) -> str:
    """Fallback grep-style search."""
    store = KnowledgeStoreService()
    
    # Compile regex pattern
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"Invalid regex pattern: {e}"
    
    # Get all documents
    documents = store.list_documents(collection or None)
    
    # Filter by path if specified
    if path:
        documents = [d for d in documents if path in d['path']]
    
    # Search documents
    matches = []
    total_matches = 0
    
    for doc in documents:
        if total_matches >= max_results:
            break
        
        doc_matches = _search_document(store, doc['path'], regex, context_lines, max_results - total_matches)
        
        if doc_matches:
            matches.append({
                "file": doc['path'],
                "title": doc.get('title', doc['path']),
                "match_count": len(doc_matches),
                "matches": doc_matches
            })
            total_matches += len(doc_matches)
    
    # Format output
    return _format_grep_results(matches, pattern, len(documents))


def _search_document(store, path: str, regex: re.Pattern, context_lines: int, max_matches: int) -> list[dict]:
    """Search a single document."""
    try:
        # Read full document
        result = store.read_document(path)
        content = result['content']
        lines = content.split('\n')
        
        matches = []
        for i, line in enumerate(lines):
            if len(matches) >= max_matches:
                break
                
            if regex.search(line):
                # Get context
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                
                matches.append({
                    "line": i + 1,
                    "text": line,
                    "context_before": lines[start:i],
                    "context_after": lines[i+1:end]
                })
        
        return matches
    
    except Exception as e:
        logger.warning(f"Failed to search {path}: {e}")
        return []


def _format_grep_results(matches: list, pattern: str, docs_searched: int) -> str:
    """Format grep search results."""
    if not matches:
        return f"No matches found for '{pattern}' (searched {docs_searched} documents)"
    
    lines = []
    total_match_count = sum(m['match_count'] for m in matches)
    lines.append(f"Grep results for: '{pattern}'")
    lines.append(f"   Found {total_match_count} matches in {len(matches)} files (searched {docs_searched} documents)")
    lines.append("")
    
    for file_match in matches:
        lines.append(f"- {file_match['file']}")
        if file_match.get('title') and file_match['title'] != file_match['file']:
            lines.append(f"   Title: {file_match['title']}")
        lines.append(f"   {file_match['match_count']} matches")
        lines.append("")
        
        # Show matches
        for match in file_match['matches']:
            # Context before
            for j, ctx_line in enumerate(match['context_before']):
                ctx_line_num = match['line'] - len(match['context_before']) + j
                lines.append(f"   {ctx_line_num:4d} | {ctx_line}")
            
            # Match line
            lines.append(f"-> {match['line']:4d} | {match['text']}")
            
            # Context after
            for j, ctx_line in enumerate(match['context_after']):
                ctx_line_num = match['line'] + 1 + j
                lines.append(f"   {ctx_line_num:4d} | {ctx_line}")
            
            lines.append("")
        
        lines.append("")
    
    return "\n".join(lines)
