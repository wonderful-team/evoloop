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


# Default bilingual tag categories (T-2.1: configurable)
_DEFAULT_TAG_CATEGORIES = {
    "type": [
        "architecture", "design", "api", "database", "frontend",
        "backend", "infrastructure", "security", "testing",
        "documentation", "guide", "tutorial", "reference",
        "架构", "设计", "接口", "数据库", "前端",
        "后端", "基础设施", "安全", "测试",
        "文档", "指南", "教程", "参考"
    ],
    "tech": [
        "python", "javascript", "typescript", "react", "vue",
        "nodejs", "fastapi", "django", "postgresql", "mongodb",
        "docker", "kubernetes", "aws", "git", "ci-cd",
        "python", "java", "go", "rust", "c++",
        "docker", "kubernetes", "linux", "nginx", "redis"
    ],
    "domain": [
        "authentication", "payment", "message", "analytics",
        "ml-ai", "blockchain", "iot", "mobile", "web",
        "认证", "支付", "消息", "分析",
        "机器学习", "区块链", "物联网", "移动", "网页"
    ],
    "priority": [
        "critical", "high", "medium", "low", "archived",
        "紧急", "高", "中", "低", "归档"
    ]
}


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

    def __init__(self, fts_service=None):
        self._tag_cache = {}  # Simple cache for common patterns
        self._tag_categories: dict[str, list[str]] | None = None
        self._all_valid_tags: set[str] | None = None
        self._fts = fts_service
    
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
        
        # Ensure tags are loaded
        self._ensure_tags_loaded()

        # Build prompt
        valid_tags_list = ", ".join(sorted(self._all_valid_tags))
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
            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=[{"role": "user", "content": prompt}],
                purpose="memory_extraction",
                temperature=0.3,
                model_name=model_name,
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
    
    def _ensure_tags_loaded(self) -> None:
        """Lazy-load tag configuration from DB or defaults."""
        if self._tag_categories is not None:
            return
        if self._fts is not None:
            try:
                self._load_tags_from_db()
                return
            except Exception as e:
                logger.warning(f"Failed to load tags from DB: {e}, using defaults")
        self._tag_categories = {k: list(v) for k, v in _DEFAULT_TAG_CATEGORIES.items()}
        self._all_valid_tags = set()
        for category in self._tag_categories.values():
            self._all_valid_tags.update(category)

    def _load_tags_from_db(self) -> None:
        """Load enabled tags from search database."""
        rows = self._fts.get_tag_config()
        categories: dict[str, list[str]] = {}
        for row in rows:
            cat = row.get("category", "type")
            categories.setdefault(cat, []).append(row["tag"])
        if categories:
            self._tag_categories = categories
            self._all_valid_tags = set()
            for cat_tags in categories.values():
                self._all_valid_tags.update(cat_tags)
        else:
            self._tag_categories = {k: list(v) for k, v in _DEFAULT_TAG_CATEGORIES.items()}
            self._all_valid_tags = set()
            for category in self._tag_categories.values():
                self._all_valid_tags.update(category)

    def _validate_tags(self, tags: list[str]) -> list[str]:
        """Validate and normalize tags."""
        self._ensure_tags_loaded()
        validated = []
        for tag in tags:
            tag = tag.lower().strip().replace(" ", "-")
            if tag in self._all_valid_tags:
                validated.append(tag)
            elif len(tag) > 2:  # Allow custom tags if reasonable length
                validated.append(tag)
        return validated
    
    def _fallback_tagging(self, title: str, content: str) -> TaggingResult:
        """Simple rule-based tagging when LLM fails."""
        self._ensure_tags_loaded()
        tags = []
        text = (title + " " + content[:1000]).lower()

        # Dynamic keyword matching from configured tags
        keyword_tags = {
            "authentication": ["auth", "login", "jwt", "oauth", "password", "认证", "登录"],
            "api": ["api", "endpoint", "rest", "graphql", "接口", "api"],
            "database": ["database", "sql", "postgres", "mongo", "redis", "数据库"],
            "frontend": ["react", "vue", "angular", "css", "html", "ui", "前端"],
            "backend": ["server", "api", "fastapi", "django", "flask", "后端"],
            "infrastructure": ["docker", "kubernetes", "k8s", "aws", "deployment", "基础设施", "部署"],
            "security": ["security", "vulnerability", "encryption", "xss", "csrf", "安全"],
            "testing": ["test", "testing", "jest", "pytest", "cypress", "测试"],
            "documentation": ["readme", "documentation", "guide", "tutorial", "文档", "指南"],
            "ml-ai": ["machine learning", "ml", "ai", "deep learning", "model", "机器学习", "人工智能"],
            "blockchain": ["blockchain", "crypto", "web3", "区块链"],
        }

        for tag, keywords in keyword_tags.items():
            if any(kw in text for kw in keywords):
                tags.append(tag)

        # Determine category from configured taxonomy
        category = "type"
        for cat, cat_tags in self._tag_categories.items() if self._tag_categories else _DEFAULT_TAG_CATEGORIES.items():
            if any(t in cat_tags for t in tags):
                category = cat
                break

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
        self._ensure_tags_loaded()
        query_lower = query.lower()
        suggestions = []

        # Match against valid tags
        for tag in self._all_valid_tags:
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

        Returns tags from the same category based on configured taxonomy.
        """
        self._ensure_tags_loaded()
        related = set()

        categories = self._tag_categories or _DEFAULT_TAG_CATEGORIES
        for tag in tags:
            # Find which category this tag belongs to
            for cat_tags in categories.values():
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
