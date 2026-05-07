"""
Unit tests for stopword filtering.

Run with: pytest tests/unit/memory/test_stopwords.py -v
"""

import pytest


class TestStopwordFiltering:
    """Tests for English and Chinese stopword detection."""

    def test_english_stopwords_filtered(self):
        from app.core.memory.stopwords import is_stopword

        assert is_stopword("the") is True
        assert is_stopword("is") is True
        assert is_stopword("a") is True
        assert is_stopword("should") is True
        assert is_stopword("and") is True

    def test_english_technical_terms_preserved(self):
        from app.core.memory.stopwords import is_stopword

        assert is_stopword("api") is False
        assert is_stopword("function") is False
        assert is_stopword("cache") is False
        assert is_stopword("kubernetes") is False
        assert is_stopword("jwt") is False

    def test_case_insensitive(self):
        from app.core.memory.stopwords import is_stopword

        assert is_stopword("The") is True
        assert is_stopword("THE") is True
        assert is_stopword("API") is False

    def test_chinese_stopwords_filtered(self):
        from app.core.memory.stopwords import is_stopword

        assert is_stopword("的") is True
        assert is_stopword("了") is True
        assert is_stopword("在") is True
        assert is_stopword("必须") is True
        assert is_stopword("应该") is True

    def test_chinese_technical_terms_preserved(self):
        from app.core.memory.stopwords import is_stopword

        assert is_stopword("函数") is False
        assert is_stopword("缓存") is False
        assert is_stopword("数据库") is False
        assert is_stopword("异步") is False

    def test_mixed_content_tokens(self):
        """Simulate real tokenization output."""
        from app.core.memory.stopwords import ALL_STOPWORDS

        tokens = ["the", "api", "gateway", "的", "函数", "需要", "缓存"]
        filtered = [t for t in tokens if t not in ALL_STOPWORDS]

        assert "the" not in filtered
        assert "的" not in filtered
        assert "api" in filtered
        assert "函数" in filtered
        assert "缓存" in filtered
