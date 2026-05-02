"""
Document deduplication and merging service.

Identifies similar documents and provides options to:
- Detect duplicates
- Merge similar content
- Suggest canonical versions
"""

import asyncio
import hashlib
import logging
from difflib import SequenceMatcher
from typing import Optional

from pydantic import Field

from app.domain.knowledge.schemas import DuplicateResult, MergeSuggestion, MergeResult, DeleteDuplicatesResult
from app.domain.knowledge.services.store import KnowledgeStoreService
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class MinHash:
    """Locality-sensitive hashing for Jaccard similarity approximation (T-2.3)."""

    def __init__(self, num_perm: int = 128, shingle_size: int = 3):
        self.num_perm = num_perm
        self.shingle_size = shingle_size
        # Deterministic seeds for reproducible signatures across runs
        self._seeds = [
            hashlib.sha256(f"minhash_seed_{i}".encode()).hexdigest()[:16]
            for i in range(num_perm)
        ]

    def _shingles(self, text: str) -> set[str]:
        words = text.lower().split()
        if len(words) < self.shingle_size:
            return {" ".join(words)} if words else set()
        return {
            " ".join(words[i : i + self.shingle_size])
            for i in range(len(words) - self.shingle_size + 1)
        }

    def signature(self, text: str) -> list[int]:
        shingles = self._shingles(text)
        if not shingles:
            return [0] * self.num_perm
        return [
            min(
                int(hashlib.md5(f"{s}:{seed}".encode()).hexdigest(), 16)
                for s in shingles
            )
            for seed in self._seeds
        ]


class LSH:
    """Locality Sensitive Hashing buckets for candidate pair generation (T-2.3)."""

    def __init__(self, num_perm: int = 128, num_bands: int = 16):
        self.num_bands = num_bands
        self.rows_per_band = num_perm // num_bands
        self.buckets: list[dict[tuple[int, ...], list[str]]] = [
            {} for _ in range(num_bands)
        ]

    def add(self, doc_id: str, signature: list[int]) -> None:
        for band_idx in range(self.num_bands):
            start = band_idx * self.rows_per_band
            band_key = tuple(signature[start : start + self.rows_per_band])
            self.buckets[band_idx].setdefault(band_key, []).append(doc_id)

    def candidate_pairs(self) -> set[tuple[str, str]]:
        pairs: set[tuple[str, str]] = set()
        for bucket in self.buckets:
            for doc_ids in bucket.values():
                if len(doc_ids) > 1:
                    for i in range(len(doc_ids)):
                        for j in range(i + 1, len(doc_ids)):
                            pairs.add(tuple(sorted((doc_ids[i], doc_ids[j]))))
        return pairs


class DeduplicationReport(DynamicBaseModel):
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

        # Batch read to avoid N+1 file I/O
        batch = self.store.read_documents_batch([doc.path for doc in documents])

        for doc in documents:
            result = batch.get(doc.path)
            if not result:
                continue

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

            # Check content similarity (offload to thread pool to avoid blocking)
            content_sim = await asyncio.to_thread(
                self._similarity_score, content, doc_content
            )
            if content_sim >= threshold:
                similar.append(DuplicateResult(
                    doc_id=doc.path,
                    path=doc.path,
                    similarity=content_sim,
                    match_type="content",
                    suggested_action="merge" if content_sim > 0.9 else "review"
                ))
                continue

            # Check title similarity (offload to thread pool)
            title_sim = await asyncio.to_thread(
                self._similarity_score, title.lower(), doc_title.lower()
            )
            if title_sim >= 0.9:
                similar.append(DuplicateResult(
                    doc_id=doc.path,
                    path=doc.path,
                    similarity=title_sim,
                    match_type="title",
                    suggested_action="review"
                ))

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

        # Compute hashes for all documents (batch read to avoid N+1)
        doc_hashes = {}
        doc_contents = {}

        batch = self.store.read_documents_batch([doc.path for doc in documents])
        for doc in documents:
            result = batch.get(doc.path)
            if not result:
                continue
            content = result.content
            doc_contents[doc.path] = content
            doc_hashes[doc.path] = self._compute_content_hash(content)
        
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
        
        # Find similar documents using MinHash LSH (T-2.3)
        similar_groups = []
        if len(doc_contents) > 1:
            similar_groups = await self._find_similar_lsh(doc_contents)

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
        batch = self.store.read_documents_batch(paths)
        for path in paths:
            result = batch.get(path)
            if not result:
                continue
            # Extract title from content (first h1)
            content = result.content
            if content.startswith("# "):
                title = content[2:content.find('\n')]
                titles.append(title)

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
    
    async def _find_similar_lsh(
        self, doc_contents: dict[str, str], threshold: float = 0.8
    ) -> list[list[str]]:
        """Find similar document groups using MinHash + LSH (T-2.3).

        Reduces O(n²) pairwise comparisons to O(n) signature generation
        plus verification of a small candidate set.
        """

        def _build_lsh() -> LSH:
            minhash = MinHash(num_perm=128, shingle_size=3)
            lsh = LSH(num_perm=128, num_bands=16)
            for path, content in doc_contents.items():
                sig = minhash.signature(content)
                lsh.add(path, sig)
            return lsh

        lsh = await asyncio.to_thread(_build_lsh)
        candidate_pairs = await asyncio.to_thread(lsh.candidate_pairs)

        # Verify candidates with SequenceMatcher (run in thread pool)
        verified_pairs: list[tuple[float, str, str]] = []
        for path1, path2 in candidate_pairs:
            sim = await asyncio.to_thread(
                self._similarity_score, doc_contents[path1], doc_contents[path2]
            )
            if sim >= threshold:
                verified_pairs.append((sim, path1, path2))

        # Group verified pairs into connected components
        verified_pairs.sort(key=lambda x: x[0], reverse=True)
        processed: set[str] = set()
        groups: list[list[str]] = []

        for sim, path1, path2 in verified_pairs:
            if path1 in processed or path2 in processed:
                continue

            group: set[str] = {path1, path2}
            # Grow group by adding connected unprocessed documents
            changed = True
            while changed:
                changed = False
                for _, p1, p2 in verified_pairs:
                    if p1 in group and p2 not in processed and p2 not in group:
                        group.add(p2)
                        changed = True
                    elif p2 in group and p1 not in processed and p1 not in group:
                        group.add(p1)
                        changed = True

            if len(group) > 1:
                groups.append(list(group))
                processed.update(group)

        return groups

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
            # Read all documents (batch to avoid N+1)
            contents = []
            batch = self.store.read_documents_batch(source_paths)
            for path in source_paths:
                result = batch.get(path)
                if result:
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
    ) -> DeleteDuplicatesResult:
        """
        Delete duplicate documents, keeping one copy.
        
        Args:
            duplicate_pairs: Pairs of (to_delete, to_keep) or just duplicates
        
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
