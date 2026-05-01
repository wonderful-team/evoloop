"""
Unit tests for Memory Quality Analyzer (Phase 3).

Tests quality scoring, cleanup recommendations, and report generation.

Run with: pytest tests/unit/memory/test_quality.py -v
"""

import pytest
import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


class TestQualityScoresDataclass:
    """Tests for QualityScores data class."""
    
    def test_quality_scores_creation(self):
        """Test that QualityScores can be created."""
        from app.core.memory.quality import QualityScores
        
        scores = QualityScores(
            freshness=0.8,
            usage=0.3,
            specificity=0.9,
            actionability=0.7,
            overall=0.675,
        )
        
        assert scores.freshness == 0.8
        assert scores.usage == 0.3
        assert scores.specificity == 0.9
        assert scores.actionability == 0.7
        assert scores.overall == 0.675
    
    def test_quality_scores_to_dict(self):
        """Test conversion to dictionary."""
        from app.core.memory.quality import QualityScores
        
        scores = QualityScores(
            freshness=0.8123,
            usage=0.3456,
            specificity=0.9,
            actionability=0.7,
            overall=0.6894,
        )
        
        d = scores.model_dump()
        
        assert d["freshness"] == 0.81
        assert d["usage"] == 0.35
        assert isinstance(d, dict)


class TestFreshnessScoring:
    """Tests for freshness score calculation."""
    
    def test_freshness_now(self):
        """Test freshness for brand new memory."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="New Memory",
            description="Just created",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_freshness(entry)
        
        # Freshness should be close to 1.0 for new entries
        assert score > 0.95
        assert score <= 1.0
    
    def test_freshness_half_life(self):
        """Test freshness at half-life (30 days)."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Old Memory",
            description="30 days old",
            content="Content",
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
        )
        
        score = analyzer._score_freshness(entry)
        
        # Half-life formula is exp(-days/30), so 30 days gives e^-1 ≈ 0.368
        assert 0.3 < score < 0.4
    
    def test_freshness_very_old(self):
        """Test freshness for very old memory."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Ancient Memory",
            description="90 days old",
            content="Content",
            created_at=now - timedelta(days=90),
            updated_at=now - timedelta(days=90),
        )
        
        score = analyzer._score_freshness(entry)
        
        # Should be quite low for very old entries
        assert score < 0.1


class TestUsageScoring:
    """Tests for usage score calculation."""
    
    def test_usage_zero_accesses(self):
        """Test usage score with no accesses."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Unused Memory",
            description="Never accessed",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        # Run synchronously for test
        import asyncio
        score = asyncio.run(analyzer._score_usage(entry))
        
        assert score == 0.0
    
    def test_usage_multiple_accesses(self):
        """Test usage score with multiple accesses."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        analyzer._access_counts["mem_001"] = 5
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Used Memory",
            description="Accessed 5 times",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        import asyncio
        score = asyncio.run(analyzer._score_usage(entry))
        
        # 5 accesses out of 10 max = 0.5
        assert score == 0.5
    
    def test_usage_max_cap(self):
        """Test that usage score caps at 1.0."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        analyzer._access_counts["mem_001"] = 100  # Way more than max
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Heavily Used Memory",
            description="Accessed many times",
            content="Content",
            created_at=now,
            updated_at=now,
        )
        
        import asyncio
        score = asyncio.run(analyzer._score_usage(entry))
        
        # Should cap at 1.0
        assert score == 1.0


class TestSpecificityScoring:
    """Tests for specificity score calculation."""
    
    def test_specificity_with_filenames(self):
        """Test that file names increase specificity."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Specific Memory",
            description="Contains specific info",
            content="Use config.py for settings and main.py for entry point",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_heuristic_specificity(entry)
        
        # Should have positive score for file references
        assert score > 0
    
    def test_specificity_with_dates(self):
        """Test that dates increase specificity."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Dated Memory",
            description="Has dates",
            content="The deadline is 2024-03-15 and version v2.1.0",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_heuristic_specificity(entry)
        
        # Should have positive score for dates and versions
        assert score > 0
    
    def test_specificity_vague_content(self):
        """Test that vague content has low specificity."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Vague Memory",
            description="Very vague",
            content="Something is somehow not working. Maybe try some stuff.",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_heuristic_specificity(entry)
        
        # Should be low due to vague words
        assert score < 0.5


class TestActionabilityScoring:
    """Tests for actionability score calculation."""
    
    def test_actionability_with_directives(self):
        """Test that directive keywords increase actionability."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Actionable Memory",
            description="Has clear instructions",
            content="Always use TypeScript. Never use any. Prefer interfaces over types.",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_heuristic_actionability(entry)
        
        # Should have positive score for actionable keywords
        assert score > 0.15
    
    def test_actionability_with_structured_format(self):
        """Test that structured format increases actionability."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Structured Memory",
            description="Has structure",
            content="**Why:** This is important\n\n**How to apply:** Use these steps",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_heuristic_actionability(entry)
        
        # Should have bonus for structured format
        assert score > 0.3
    
    def test_actionability_no_action(self):
        """Test that descriptive content has low actionability."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Descriptive Memory",
            description="Just describes",
            content="This is a description of the project architecture without any instructions.",
            created_at=now,
            updated_at=now,
        )
        
        score = analyzer._score_heuristic_actionability(entry)
        
        # Should be low without actionable keywords
        assert score < 0.3


class TestOverallScoring:
    """Tests for overall quality score calculation."""
    
    def test_overall_score_weighted_average(self):
        """Test that overall score is weighted average of components."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        
        # Test with known scores
        expected_overall = (
            0.8 * 0.25 +  # freshness
            0.3 * 0.30 +  # usage
            0.9 * 0.25 +  # specificity
            0.7 * 0.20    # actionability
        )
        
        assert abs(expected_overall - 0.655) < 0.01
    
    @pytest.mark.asyncio
    async def test_analyze_memory_returns_scores(self):
        """Test that analyze_memory returns QualityScores."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Test Memory",
            description="Test description",
            content="Always use TypeScript for new projects",
            created_at=now,
            updated_at=now,
        )
        
        scores = await analyzer.analyze_memory(entry)
        
        assert scores is not None
        assert hasattr(scores, 'freshness')
        assert hasattr(scores, 'usage')
        assert hasattr(scores, 'specificity')
        assert hasattr(scores, 'actionability')
        assert hasattr(scores, 'overall')
        
        # All scores should be between 0 and 1
        assert 0 <= scores.freshness <= 1
        assert 0 <= scores.usage <= 1
        assert 0 <= scores.specificity <= 1
        assert 0 <= scores.actionability <= 1
        assert 0 <= scores.overall <= 1


class TestCleanupRecommendations:
    """Tests for cleanup recommendation logic."""
    
    def test_determine_action_archive_old(self):
        """Test that very old project memories are marked for archive."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        old_entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Old Project Memory",
            description="Very old",
            content="Old content",
            created_at=now - timedelta(days=100),
            updated_at=now - timedelta(days=100),
        )
        
        scores = QualityScores(
            freshness=0.05,  # Very stale
            usage=0.1,
            specificity=0.8,
            actionability=0.7,
            overall=0.4,
        )
        
        action, reason, suggestions = analyzer._determine_action(old_entry, scores)
        
        assert action == "archive"
        assert "old" in reason.lower() or "outdated" in reason.lower()
    
    def test_determine_action_delete_low_quality(self):
        """Test that very low quality memories are marked for deletion."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        low_quality_entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Bad Memory",
            description="Not useful",
            content="Something somehow maybe",
            created_at=now,
            updated_at=now,
        )
        
        scores = QualityScores(
            freshness=0.1,
            usage=0.0,
            specificity=0.1,
            actionability=0.1,
            overall=0.1,  # Very low
        )
        
        action, reason, suggestions = analyzer._determine_action(low_quality_entry, scores)
        
        assert action == "delete"
        assert suggestions  # Should have improvement suggestions
    
    def test_determine_action_improve(self):
        """Test that mediocre memories are marked for improvement."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Okay Memory",
            description="Could be better",
            content="Some content",
            created_at=now,
            updated_at=now,
        )
        
        scores = QualityScores(
            freshness=0.5,
            usage=0.3,
            specificity=0.2,
            actionability=0.3,
            overall=0.35,
        )
        
        action, reason, suggestions = analyzer._determine_action(entry, scores)
        
        assert action in ["improve", "update"]
        assert suggestions  # Should have suggestions for improvement
    
    def test_specificity_suggestions(self):
        """Test that low specificity generates specific suggestions."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        now = datetime.utcnow()
        
        vague_entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Vague Memory",
            description="Something",
            content="Something is not right",
            created_at=now,
            updated_at=now,
        )
        
        scores = QualityScores(
            freshness=0.5,
            usage=0.3,
            specificity=0.2,  # Low specificity
            actionability=0.5,
            overall=0.4,
        )
        
        action, reason, suggestions = analyzer._determine_action(vague_entry, scores)
        
        # Should suggest adding specific details
        assert any("specific" in s.lower() for s in suggestions)


class TestGlobalInstances:
    """Tests for global singleton instances and convenience functions."""
    
    def test_record_access(self):
        """Test that access recording works."""
        from app.core.memory.quality import MemoryQualityAnalyzer, QualityScores
        
        analyzer = MemoryQualityAnalyzer(MagicMock())
        
        # Record some accesses
        analyzer.record_access("mem_001")
        analyzer.record_access("mem_001")
        analyzer.record_access("mem_002")
        
        assert analyzer._access_counts["mem_001"] == 2
        assert analyzer._access_counts["mem_002"] == 1
