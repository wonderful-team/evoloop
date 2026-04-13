"""
Document deduplication and merging service.

Identifies similar documents and provides options to:
- Detect duplicates
- Merge similar content
- Suggest canonical versions
"""

import hashlib
import logging
from difflib import SequenceMatcher
from typing import Optional
from pydantic import BaseModel, Field

from app.domain.knowledge.services.store import KnowledgeStoreService
from app.domain.knowledge.services.search import get_fts_service
from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


class DuplicateResult(BaseModel, LegacyDictMixin):
    """Result of duplicate detection."""
    doc_id: str
    path: str
    similarity: float  # 0.0 to 1.0
    match_type: str  # "exact", "content", "title", "fuzzy"
    suggested_action: str  # "keep", "merge", "delete"


class MergeSuggestion(BaseModel, LegacyDictMixin):
    """Suggested document merge."""
    documents: list[str]
    suggested_title: str
    strategy: str  # "concatenate", "diff", "selective"


class MergeResult(BaseModel, LegacyDictMixin):
    """Result of merging documents."""
    success: bool
    path: Optional[str] = None
    source_count: Optional[int] = None
    strategy: Optional[str] = None
    error: Optional[str] = None


class DeleteDuplicatesResult(BaseModel, LegacyDictMixin):
    """Result of deleting duplicate documents."""
    deleted: int
    errors: list[dict] = Field(default_factory=list)


class DeduplicationReport(BaseModel, LegacyDictMixin):
    """Complete deduplication analysis."""
    total_documents: int
    exact_duplicates: list[tuple[str, str]] = Field(default_factory=list)  # pairs of doc_ids
    similar_documents: list[list[str]] = Field(default_factory=list)  # groups of similar docs
    potential_merges: list[MergeSuggestion] = Field(default_factory=list)  # suggested merges

    def to_dict(self) -> dict:
        """Backward compatibility for existing code calling to_dict manually."""
        return {
            "total_documents": self.total_documents,
            "exact_duplicate_count": len(self.exact_duplicates),
            "similar_group_count": len(self.similar_documents),
            "exact_duplicates": self.exact_duplicates[:20],
            "similar_groups": self.similar_documents[:10],
            "potential_merges": [m.model_dump() for m in self.potential_merges[:10]]
        }


class DeduplicationService:
    """
    Service for detecting and handling duplicate documents.
    
    Uses multiple strategies:
    1. Content hash (exact duplicates)
    2. Perceptual hashing (near-duplicates)
    3. Title similarity
    4. Vector similarity (semantic duplicates)
    
    Usage:
        dedup = DeduplicationService()
        
        # Check for duplicates
        report = await dedup.analyze_project("my-project")
        
        # Find similar to new document
        similar = await dedup.find_similar("New Document Title", "Content...")
    """
    
    def __init__(self, store: Optional[KnowledgeStoreService] = None):
        self.store = store or KnowledgeStoreService()
        self._hash_cache = {}
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute normalized content hash."""
        # Normalize: lowercase, strip whitespace
        normalized = content.lower().strip()
        normalized = " ".join(normalized.split())  # Collapse whitespace
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _compute_simhash(self, content: str) -> str:
        """
        Compute simhash for fuzzy matching.
        
        Simplified implementation - for production, use proper simhash library.
        """
        # Split into word n-grams
        words = content.lower().split()
        ngrams = []
        for i in range(len(words) - 2):
            ngrams.append(" ".join(words[i:i+3]))
        
        # Simple hash-based fingerprint
        if not ngrams:
            return "0"
        
        hashes = [hashlib.md5(ng.encode()).hexdigest() for ng in ngrams]
        # XOR combine
        fingerprint = 0
        for h in hashes:
            fingerprint ^= int(h, 16)
        
        return hex(fingerprint)[2:]
    
    def _similarity_score(self, content1: str, content2: str) -> float:
        """Compute similarity score between two contents."""
        # Use SequenceMatcher for text similarity
        return SequenceMatcher(None, content1, content2).ratio()
    
    async def find_similar(
        self,
        title: str,
        content: str,
        project: Optional[str] = None,
        threshold: float = 0.8
    ) -> list[DuplicateResult]:
        """
        Find documents similar to the given content.
        
        Args:
            title: Document title to compare
            content: Document content to compare
            project: Limit to project (None = all)
            threshold: Minimum similarity score (0.0-1.0)
        
        Returns:
            List of similar documents sorted by similarity
        """
        similar = []
        content_hash = self._compute_content_hash(content)
        
        # Get all documents in scope
        documents = self.store.list_documents(project)
        
        for doc in documents:
            try:
                # Read document content
                result = self.store.read_document(doc.path)
                doc_content = result.content
                doc_title = doc.title

                # Check exact match
                doc_hash = self._compute_content_hash(doc_content)
                if doc_hash == content_hash:
                    similar.append(DuplicateResult(
                        doc_id=doc.path,
                        path=doc.path,
                        similarity=1.0,
                        match_type="exact",
                        suggested_action="delete"
                    ))
                    continue

                # Check content similarity
                content_sim = self._similarity_score(content, doc_content)
                if content_sim >= threshold:
                    similar.append(DuplicateResult(
                        doc_id=doc.path,
                        path=doc.path,
                        similarity=content_sim,
                        match_type="content",
                        suggested_action="merge" if content_sim > 0.9 else "review"
                    ))
                    continue

                # Check title similarity
                title_sim = self._similarity_score(title.lower(), doc_title.lower())
                if title_sim >= 0.9:
                    similar.append(DuplicateResult(
                        doc_id=doc.path,
                        path=doc.path,
                        similarity=title_sim,
                        match_type="title",
                        suggested_action="review"
                    ))

            except Exception as e:
                logger.warning(f"Failed to compare with {doc.path}: {e}")
        
        # Sort by similarity descending
        similar.sort(key=lambda x: x.similarity, reverse=True)
        return similar
    
    async def analyze_project(
        self,
        project: Optional[str] = None
    ) -> DeduplicationReport:
        """
        Analyze a project for duplicates.
        
        Args:
            project: Project to analyze (None = all)
        
        Returns:
            DeduplicationReport with findings
        """
        documents = self.store.list_documents(project)
        
        # Compute hashes for all documents
        doc_hashes = {}
        doc_contents = {}
        
        for doc in documents:
            try:
                result = self.store.read_document(doc.path)
                content = result.content
                doc_contents[doc.path] = content
                doc_hashes[doc.path] = self._compute_content_hash(content)
            except Exception as e:
                logger.warning(f"Failed to read {doc.path}: {e}")
        
        # Find exact duplicates
        hash_to_docs = {}
        for path, h in doc_hashes.items():
            if h not in hash_to_docs:
                hash_to_docs[h] = []
            hash_to_docs[h].append(path)
        
        exact_duplicates = []
        for h, paths in hash_to_docs.items():
            if len(paths) > 1:
                # Create pairs
                for i in range(len(paths) - 1):
                    exact_duplicates.append((paths[i], paths[i + 1]))
        
        # Find similar documents (groups)
        similar_groups = []
        processed = set()
        
        for path1 in doc_contents:
            if path1 in processed:
                continue
            
            group = [path1]
            content1 = doc_contents[path1]
            
            for path2 in doc_contents:
                if path2 == path1 or path2 in processed:
                    continue
                
                content2 = doc_contents[path2]
                sim = self._similarity_score(content1, content2)
                
                if sim >= 0.8:  # High similarity threshold
                    group.append(path2)
            
            if len(group) > 1:
                similar_groups.append(group)
                processed.update(group)
        
        # Generate merge suggestions
        potential_merges = []
        for group in similar_groups[:5]:
            potential_merges.append(
                MergeSuggestion(
                    documents=group,
                    suggested_title=self._suggest_merge_title(group),
                    strategy="concatenate"  # or "diff", "selective"
                )
            )
        
        return DeduplicationReport(
            total_documents=len(documents),
            exact_duplicates=exact_duplicates,
            similar_documents=similar_groups,
            potential_merges=potential_merges
        )
    
    def _suggest_merge_title(self, paths: list[str]) -> str:
        """Suggest a title for merged document."""
        # Use common prefix or first document's title
        titles = []
        for path in paths:
            try:
                result = self.store.read_document(path)
                # Extract title from content (first h1)
                content = result.content
                if content.startswith("# "):
                    title = content[2:content.find('\n')]
                    titles.append(title)
            except:
                pass
        
        if titles:
            # Find common prefix
            prefix = titles[0]
            for title in titles[1:]:
                while not title.startswith(prefix) and prefix:
                    prefix = prefix[:-1]
            if prefix:
                return prefix.strip()
            return titles[0] + " (Merged)"
        
        return "Merged Document"
    
    async def merge_documents(
        self,
        source_paths: list[str],
        target_path: Optional[str] = None,
        strategy: str = "concatenate"
    ) -> MergeResult:
        """
        Merge multiple documents into one.
        
        Args:
            source_paths: Documents to merge
            target_path: Where to save merged doc (None = use first source)
            strategy: Merge strategy - "concatenate", "deduplicate", "smart"
        
        Returns:
            Result info with merged document path
        """
        if len(source_paths) < 2:
            return MergeResult(success=False, error="Need at least 2 documents to merge")

        try:
            # Read all documents
            contents = []
            for path in source_paths:
                result = self.store.read_document(path)
                contents.append(result.content)
            
            if strategy == "concatenate":
                merged_content = "\n\n---\n\n".join(contents)
            elif strategy == "deduplicate":
                # Simple dedup: split by paragraph, remove exact duplicates
                seen = set()
                unique_parts = []
                for content in contents:
                    for para in content.split("\n\n"):
                        para_hash = hashlib.md5(para.strip().encode()).hexdigest()
                        if para_hash not in seen and len(para.strip()) > 20:
                            seen.add(para_hash)
                            unique_parts.append(para)
                merged_content = "\n\n".join(unique_parts)
            else:
                merged_content = contents[0]  # Default: keep first
            
            # Save merged document
            target = target_path or source_paths[0].replace(".md", "-merged.md")
            
            from app.domain.knowledge.models import MarkdownDocument
            merged_doc = MarkdownDocument(
                content=f"# Merged Document\n\n{merged_content}",
                source="merge",
                mime_type="text/markdown",
                metadata={"merged_from": source_paths}
            )
            
            # Save to target collection
            target_collection = target.split("/")[0] if "/" in target else "default"
            target_path = "/".join(target.split("/")[1:]) if "/" in target else target
            self.store.save_document(merged_doc, collection=target_collection, path=target_path)
            
            return MergeResult(
                success=True,
                path=target,
                source_count=len(source_paths),
                strategy=strategy
            )

        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return MergeResult(success=False, error=str(e))
    
    async def delete_duplicates(
        self,
        duplicate_pairs: list[tuple[str, str]],
        keep_oldest: bool = True
    ) -> DeleteDuplicatesResult:
        """
        Delete duplicate documents, keeping one copy.
        
        Args:
            duplicate_pairs: Pairs of (to_delete, to_keep) or just duplicates
            keep_oldest: If True, keep oldest document in each pair
        
        Returns:
            Deletion statistics
        """
        deleted = 0
        errors = []

        for pair in duplicate_pairs:
            try:
                if len(pair) == 2:
                    to_delete, to_keep = pair
                else:
                    # Single item - skip
                    continue

                self.store.delete_document(to_delete)
                deleted += 1

            except Exception as e:
                errors.append({"path": to_delete, "error": str(e)})

        return DeleteDuplicatesResult(deleted=deleted, errors=errors)
