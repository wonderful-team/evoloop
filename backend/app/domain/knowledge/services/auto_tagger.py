"""
Automatic document tagging service using LLM.

Analyzes document content and generates relevant tags for categorization.
"""

import json
import logging
from typing import Optional

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


# Predefined tag categories for consistency
TAG_CATEGORIES = {
    "type": [
        "architecture", "design", "api", "database", "frontend",
        "backend", "infrastructure", "security", "testing",
        "documentation", "guide", "tutorial", "reference"
    ],
    "tech": [
        "python", "javascript", "typescript", "react", "vue",
        "nodejs", "fastapi", "django", "postgresql", "mongodb",
        "docker", "kubernetes", "aws", "git", "ci-cd"
    ],
    "domain": [
        "authentication", "payment", "messaging", "analytics",
        "ml-ai", "blockchain", "iot", "mobile", "web"
    ],
    "priority": [
        "critical", "high", "medium", "low", "archived"
    ]
}

# Flatten all valid tags
ALL_VALID_TAGS = set()
for category in TAG_CATEGORIES.values():
    ALL_VALID_TAGS.update(category)


class TaggingResult(DynamicBaseModel):
    """Result of auto-tagging."""
    tags: list[str] = Field(default_factory=list)
    category: str  # primary category
    confidence: float
    summary: str  # brief summary of document
    keywords: list[str] = Field(default_factory=list)  # extracted keywords


class AutoTaggerService:
    """
    Service for automatic document tagging using LLM.
    
    Usage:
        tagger = AutoTaggerService()
        result = await tagger.tag_document(
            title="JWT Authentication Guide",
            content="JSON Web Tokens are used for...",
            existing_tags=["auth"]
        )
        # result.tags = ["authentication", "security", "api", "guide"]
    """
    
    def __init__(self):
        self._tag_cache = {}  # Simple cache for common patterns
    
    async def tag_document(
        self,
        title: str,
        content: str,
        existing_tags: Optional[list[str]] = None,
        max_tags: int = 5
    ) -> TaggingResult:
        """
        Generate tags for a document using LLM.
        
        Args:
            title: Document title
            content: Document content (can be truncated)
            existing_tags: Tags already assigned
            max_tags: Maximum number of tags to generate
        
        Returns:
            TaggingResult with tags and metadata
        """
        # Truncate content if too long
        content_preview = content[:3000] if len(content) > 3000 else content
        
        # Build prompt
        valid_tags_list = ", ".join(sorted(ALL_VALID_TAGS))
        existing = ", ".join(existing_tags) if existing_tags else "none"
        
        prompt = f"""Analyze this document and generate appropriate tags.

Title: {title}

Content:
{content_preview}

Existing tags: {existing}

Valid tag options:
{valid_tags_list}

Instructions:
1. Select 3-{max_tags} most relevant tags from the valid options above
2. You may suggest 1-2 new tags if none of the existing ones fit perfectly
3. Identify the primary category (type/tech/domain/priority)
4. Provide a brief 1-sentence summary
5. Extract 5-10 key technical keywords

Respond in this exact JSON format:
{{
    "tags": ["tag1", "tag2", "tag3"],
    "category": "type",
    "confidence": 0.85,
    "summary": "Brief description of what this document covers",
    "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

        try:
            from app.core.llm import InternalLLMService
            response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": prompt}],
                purpose="memory_extraction",
                temperature=0.3,
            )
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Parse JSON response
            try:
                data = json.loads(response_text.strip())
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                if "```json" in response_text:
                    json_str = response_text.split("```json")[1].split("```")[0]
                    data = json.loads(json_str.strip())
                elif "```" in response_text:
                    json_str = response_text.split("```")[1].split("```")[0]
                    data = json.loads(json_str.strip())
                else:
                    raise
            
            # Validate and clean tags
            tags = self._validate_tags(data.get("tags", []))
            
            return TaggingResult(
                tags=tags[:max_tags],
                category=data.get("category", "type"),
                confidence=float(data.get("confidence", 0.5)),
                summary=data.get("summary", ""),
                keywords=data.get("keywords", [])
            )
        
        except Exception as e:
            logger.error(f"Auto-tagging failed: {e}")
            # Fallback to basic tagging
            return self._fallback_tagging(title, content)
    
    def _validate_tags(self, tags: list[str]) -> list[str]:
        """Validate and normalize tags."""
        validated = []
        for tag in tags:
            tag = tag.lower().strip().replace(" ", "-")
            if tag in ALL_VALID_TAGS:
                validated.append(tag)
            elif len(tag) > 2:  # Allow custom tags if reasonable length
                validated.append(tag)
        return validated
    
    def _fallback_tagging(self, title: str, content: str) -> TaggingResult:
        """Simple rule-based tagging when LLM fails."""
        tags = []
        text = (title + " " + content[:1000]).lower()
        
        # Simple keyword matching
        keyword_tags = {
            "authentication": ["auth", "login", "jwt", "oauth", "password"],
            "api": ["api", "endpoint", "rest", "graphql"],
            "database": ["database", "sql", "postgres", "mongo", "redis"],
            "frontend": ["react", "vue", "angular", "css", "html", "ui"],
            "backend": ["server", "api", "fastapi", "django", "flask"],
            "infrastructure": ["docker", "kubernetes", "k8s", "aws", "deployment"],
            "security": ["security", "vulnerability", "encryption", "xss", "csrf"],
            "testing": ["test", "testing", "jest", "pytest", "cypress"],
            "documentation": ["readme", "documentation", "guide", "tutorial"],
        }
        
        for tag, keywords in keyword_tags.items():
            if any(kw in text for kw in keywords):
                tags.append(tag)
        
        # Determine category
        category = "type"
        if any(t in tags for t in ["python", "javascript", "react"]):
            category = "tech"
        elif any(t in tags for t in ["authentication", "payment"]):
            category = "domain"
        
        return TaggingResult(
            tags=tags[:5],
            category=category,
            confidence=0.5,
            summary=f"Document about {', '.join(tags[:3]) if tags else 'general topics'}",
            keywords=[]
        )
    
    async def suggest_tags_for_query(self, query: str) -> list[str]:
        """
        Suggest tags based on a search query.
        
        Useful for auto-completing tag searches.
        """
        query_lower = query.lower()
        suggestions = []
        
        # Match against valid tags
        for tag in ALL_VALID_TAGS:
            if query_lower in tag or tag in query_lower:
                suggestions.append(tag)
        
        # Sort by relevance (exact match first)
        suggestions.sort(key=lambda t: (
            0 if t == query_lower else 1,
            0 if t.startswith(query_lower) else 1,
            len(t)
        ))
        
        return suggestions[:10]
    
    async def get_related_tags(self, tags: list[str]) -> list[str]:
        """
        Get tags commonly used together with the given tags.
        
        This would typically query the database for co-occurrence.
        For now, return tags from the same category.
        """
        related = set()
        
        for tag in tags:
            # Find which category this tag belongs to
            for category, cat_tags in TAG_CATEGORIES.items():
                if tag in cat_tags:
                    # Add other tags from same category
                    related.update(t for t in cat_tags if t != tag)
        
        return list(related)[:10]


# Singleton instance
_auto_tagger: Optional[AutoTaggerService] = None


def get_auto_tagger() -> AutoTaggerService:
    """Get or create auto-tagger singleton."""
    global _auto_tagger
    if _auto_tagger is None:
        _auto_tagger = AutoTaggerService()
    return _auto_tagger
