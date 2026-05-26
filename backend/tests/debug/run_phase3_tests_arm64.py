#!/usr/bin/env python3
"""
ARM64 Test Runner for Phase 3 Memory System.

Usage:
    arch -arm64 python3 tests/run_phase3_tests_arm64.py

This script runs all Phase 3 tests directly without pytest
to avoid version compatibility issues.
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, '.')


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add_pass(self, name):
        self.passed += 1
        self.tests.append(("PASS", name))
        print(f"  ✓ {name}")
    
    def add_fail(self, name, error):
        self.failed += 1
        self.tests.append(("FAIL", name, error))
        print(f"  ✗ {name}: {error}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed")
        print('='*60)
        return self.failed == 0


# ============== Smart Retrieval Tests ==============

def test_smart_retriever_init():
    """Test SmartMemoryRetriever initialization."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever
    
    retriever = SmartMemoryRetriever()
    assert retriever.max_candidates == 20
    assert retriever.max_results == 5
    assert retriever.enable_llm_selection is True
    
    retriever2 = SmartMemoryRetriever(max_candidates=50, max_results=10, enable_llm_selection=False)
    assert retriever2.max_candidates == 50
    assert retriever2.max_results == 10
    assert retriever2.enable_llm_selection is False


def test_candidate_keyword_scoring():
    """Test candidate keyword scoring."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    entry = MemoryEntry(
        id="mem_001",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Docker Best Practices",
        description="How to use Docker effectively",
        content="Always use multi-stage builds",
        created_at=now,
        updated_at=now,
    )
    
    ctx = RetrievalContext(
        query="Docker best practices",
        recent_tools=[],
        already_surfaced=set(),
    )
    
    score = retriever._score_candidate(entry, ctx)
    assert score > 0


def test_freshness_boost():
    """Test freshness boost in scoring."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    fresh_entry = MemoryEntry(
        id="mem_fresh",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Docker Guide 2024",
        description="Latest Docker practices",
        content="Use Docker Compose v2",
        created_at=now,
        updated_at=now,
    )
    
    old_entry = MemoryEntry(
        id="mem_old",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Docker Guide 2023",
        description="Old Docker practices",
        content="Use Docker Compose v1",
        created_at=now - timedelta(days=90),
        updated_at=now - timedelta(days=90),
    )
    
    ctx = RetrievalContext(
        query="Docker guide",
        recent_tools=[],
        already_surfaced=set(),
    )
    
    fresh_score = retriever._score_candidate(fresh_entry, ctx)
    old_score = retriever._score_candidate(old_entry, ctx)
    
    assert fresh_score > old_score


def test_type_priority():
    """Test type priority multipliers."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever, RetrievalContext
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    base_kwargs = {
        "privacy": PrivacyLevel.PRIVATE,
        "title": "Test",
        "description": "Test desc",
        "content": "Test content",
        "created_at": now,
        "updated_at": now,
    }
    
    user_entry = MemoryEntry(id="mem_user", type=MemoryType.USER, **base_kwargs)
    feedback_entry = MemoryEntry(id="mem_feedback", type=MemoryType.FEEDBACK, **base_kwargs)
    project_entry = MemoryEntry(id="mem_project", type=MemoryType.PROJECT, **base_kwargs)
    reference_entry = MemoryEntry(id="mem_reference", type=MemoryType.REFERENCE, **base_kwargs)
    
    ctx = RetrievalContext(query="test", recent_tools=[], already_surfaced=set())
    
    user_score = retriever._score_candidate(user_entry, ctx)
    feedback_score = retriever._score_candidate(feedback_entry, ctx)
    project_score = retriever._score_candidate(project_entry, ctx)
    reference_score = retriever._score_candidate(reference_entry, ctx)
    
    assert user_score > feedback_score
    assert feedback_score > project_score
    assert project_score > reference_score


def test_recent_tool_filtering():
    """Test filtering of recent tools."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    # Memory about docker (should be filtered)
    docker_memory = MemoryEntry(
        id="mem_001",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Docker Configuration",
        description="How to configure Docker containers",
        content="Use docker-compose for orchestration with docker",
        created_at=now,
        updated_at=now,
    )
    
    # Memory about kubernetes (should not be filtered)
    k8s_memory = MemoryEntry(
        id="mem_002",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Kubernetes Guide",
        description="Kubernetes deployment patterns",
        content="Use helm charts for deployment",
        created_at=now,
        updated_at=now,
    )
    
    candidates = [docker_memory, k8s_memory]
    # "docker" is in recent_tools and in docker_memory content
    filtered = retriever._filter_recent_tools(candidates, ["docker"])
    
    assert len(filtered) == 1
    assert filtered[0].id == "mem_002"


def test_keep_warnings_with_recent_tools():
    """Test that warnings are kept even for recent tools."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    warning_memory = MemoryEntry(
        id="mem_001",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Docker Warning",
        description="Important caution about Docker",
        content="Warning: Don't use docker-compose in production without proper security",
        created_at=now,
        updated_at=now,
    )
    
    candidates = [warning_memory]
    filtered = retriever._filter_recent_tools(candidates, ["docker"])
    
    assert len(filtered) == 1


def test_llm_response_parsing():
    """Test parsing of LLM selection response."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    candidates = [
        MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                   title="A", description="D", content="C", created_at=now, updated_at=now),
        MemoryEntry(id="mem_002", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                   title="B", description="D", content="C", created_at=now, updated_at=now),
    ]
    
    response = '{"selected_indices": [1], "reasoning": "Good match"}'
    selected_ids = retriever._parse_selection_response(response, candidates)
    
    assert len(selected_ids) == 1
    assert "mem_001" in selected_ids


def test_llm_response_parsing_codeblock():
    """Test parsing JSON in code block."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever()
    now = datetime.utcnow()
    
    candidates = [
        MemoryEntry(id="mem_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                   title="A", description="D", content="C", created_at=now, updated_at=now),
    ]
    
    response = '```json\n{"selected_indices": [1], "reasoning": "Good"}\n```'
    selected_ids = retriever._parse_selection_response(response, candidates)
    
    assert len(selected_ids) == 1


def test_llm_invalid_json_fallback():
    """Test fallback on invalid JSON."""
    from app.core.memory.smart_retrieval import SmartMemoryRetriever
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    retriever = SmartMemoryRetriever(max_results=2)
    now = datetime.utcnow()
    
    candidates = [
        MemoryEntry(id=f"mem_{i:03d}", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM,
                   title=f"M{i}", description="D", content="C", created_at=now, updated_at=now)
        for i in range(3)
    ]
    
    response = "This is not valid JSON"
    selected_ids = retriever._parse_selection_response(response, candidates)
    
    assert len(selected_ids) == 2
    assert "mem_000" in selected_ids
    assert "mem_001" in selected_ids


# ============== Quality Tests ==============

def test_quality_freshness_now():
    """Test freshness for new memory."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
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
    assert score > 0.95


def test_quality_freshness_old():
    """Test freshness for old memory."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
    now = datetime.utcnow()
    
    entry = MemoryEntry(
        id="mem_001",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Old Memory",
        description="90 days old",
        content="Content",
        created_at=now - timedelta(days=90),
        updated_at=now - timedelta(days=90),
    )
    
    score = analyzer._score_freshness(entry)
    assert score < 0.1


def test_quality_specificity_with_files():
    """Test specificity with file names."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
    now = datetime.utcnow()
    
    entry = MemoryEntry(
        id="mem_001",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Specific Memory",
        description="Has specific info",
        content="Use config.py for settings and main.py for entry point",
        created_at=now,
        updated_at=now,
    )
    
    score = analyzer._score_specificity(entry)
    assert score > 0


def test_quality_specificity_vague():
    """Test specificity for vague content."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
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
    
    score = analyzer._score_specificity(entry)
    assert score < 0.5


def test_quality_actionability_directives():
    """Test actionability with directives."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
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
    
    score = analyzer._score_actionability(entry)
    # Score should be positive (has actionable keywords)
    assert score > 0.15


def test_quality_actionability_descriptive():
    """Test actionability for descriptive content."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
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
    
    score = analyzer._score_actionability(entry)
    assert score < 0.3


async def test_quality_overall_score():
    """Test overall quality score calculation."""
    from app.core.memory.quality import MemoryQualityAnalyzer
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    analyzer = MemoryQualityAnalyzer()
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
    
    assert 0 <= scores.freshness <= 1
    assert 0 <= scores.usage <= 1
    assert 0 <= scores.specificity <= 1
    assert 0 <= scores.actionability <= 1
    assert 0 <= scores.overall <= 1


# ============== State Tracking Tests ==============

def test_state_tracker_init():
    """Test MemoryStateTracker initialization."""
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    assert tracker._surfaced == {}
    assert tracker.DEFAULT_SURFACE_TTL == 3600


def test_state_tracker_mark_surfaced():
    """Test marking memories as surfaced."""
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    
    tracker.mark_surfaced("thread_1", ["mem_001"])
    
    assert "thread_1" in tracker._surfaced
    assert "mem_001" in tracker._surfaced["thread_1"]


def test_state_tracker_mark_multiple():
    """Test marking multiple memories."""
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    
    tracker.mark_surfaced("thread_1", ["mem_001", "mem_002", "mem_003"])
    
    assert len(tracker._surfaced["thread_1"]) == 3


def test_state_tracker_is_surfaced():
    """Test checking if memory is surfaced."""
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    tracker.mark_surfaced("thread_1", ["mem_001"])
    
    assert tracker.is_surfaced("thread_1", "mem_001") is True
    assert tracker.is_surfaced("thread_1", "mem_999") is False


def test_state_tracker_filter_fresh():
    """Test filtering fresh memories."""
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    tracker.mark_surfaced("thread_1", ["mem_001"])
    
    class MockEntry:
        def __init__(self, id):
            self.id = id
    
    entries = [MockEntry("mem_001"), MockEntry("mem_002")]
    fresh = tracker.filter_fresh("thread_1", entries)
    
    assert len(fresh) == 1
    assert fresh[0].id == "mem_002"


def test_state_tracker_ttl_expiration():
    """Test TTL expiration."""
    import time
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    
    tracker._surfaced["thread_1"]["mem_old"] = time.time() - 7200
    
    assert tracker.is_surfaced("thread_1", "mem_old") is False


def test_state_tracker_clear_thread():
    """Test clearing thread."""
    from app.core.memory.state_tracking import MemoryStateTracker
    
    tracker = MemoryStateTracker()
    tracker.mark_surfaced("thread_1", ["mem_001"])
    
    tracker.clear_thread("thread_1")
    
    assert "thread_1" not in tracker._surfaced


def test_predictive_cache():
    """Test predictive memory cache."""
    from app.core.memory.state_tracking import PredictiveMemoryCache
    
    cache = PredictiveMemoryCache()
    
    cache.set("thread_1", "query", ["mem_001", "mem_002"])
    cached = cache.get("thread_1", "query")
    
    assert cached is not None
    assert len(cached) == 2


def test_predictive_cache_miss():
    """Test cache miss."""
    from app.core.memory.state_tracking import PredictiveMemoryCache
    
    cache = PredictiveMemoryCache()
    
    cached = cache.get("thread_1", "nonexistent")
    
    assert cached is None


# ============== Daily Log Tests ==============

async def test_daily_log_writer():
    """Test DailyLogWriter functionality."""
    import tempfile
    import shutil
    from datetime import datetime
    from app.core.memory.daily_log import DailyLogWriter
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    temp_dir = tempfile.mkdtemp()
    try:
        writer = DailyLogWriter(root_path=temp_dir)
        
        now = datetime.utcnow()
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title="Docker Best Practices",
            description="How to use Docker effectively",
            content="Always use multi-stage builds",
            created_at=now,
            updated_at=now,
        )
        
        await writer.append(entry)
        
        log_path = writer._get_log_path()
        assert log_path.exists(), "Log file should exist"
        
        content = log_path.read_text()
        assert "Docker Best Practices" in content
        
        # Read back
        entries = await writer.read_log()
        assert len(entries) == 1
        assert entries[0].memory_id == "mem_001"
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def test_log_consolidator():
    """Test LogConsolidator clustering."""
    import tempfile
    import shutil
    from datetime import datetime
    from app.core.memory.daily_log import LogConsolidator, DailyLogWriter
    from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
    
    temp_dir = tempfile.mkdtemp()
    try:
        consolidator = LogConsolidator(root_path=temp_dir)
        writer = DailyLogWriter(root_path=temp_dir)
        
        # Add multiple entries
        now = datetime.utcnow()
        for i in range(3):
            entry = MemoryEntry(
                id=f"mem_{i:03d}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM,
                title=f"Docker Guide {i}",
                description="Docker tips",
                content="Content",
                created_at=now,
                updated_at=now,
            )
            await writer.append(entry)
        
        # Test clustering
        entries = await writer.read_log()
        clusters = consolidator._cluster_entries(entries)
        assert len(clusters) > 0
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_log_entry_markdown():
    """Test LogEntry markdown conversion."""
    from datetime import datetime
    from app.core.memory.daily_log import LogEntry
    
    entry = LogEntry(
        timestamp=datetime(2026, 4, 2, 14, 30, 0),
        memory_id="mem_001",
        memory_type="project",
        title="Docker Best Practices",
        description="How to use Docker effectively",
        user_id="user_123",
        project_id=42,
    )
    
    markdown = entry.to_markdown()
    assert "mem_001" in markdown
    assert "Docker Best Practices" in markdown
    assert "PROJECT" in markdown
    assert "user:user_123" in markdown


# ============== Global Instances Tests ==============

def test_global_smart_retriever():
    """Test global smart_retriever instance."""
    from app.core.memory.smart_retrieval import smart_retriever, SmartMemoryRetriever
    
    assert isinstance(smart_retriever, SmartMemoryRetriever)


def test_global_quality_analyzer():
    """Test global quality_analyzer instance."""
    from app.core.memory.quality import quality_analyzer, MemoryQualityAnalyzer
    
    assert isinstance(quality_analyzer, MemoryQualityAnalyzer)


def test_global_memory_tracker():
    """Test global memory_tracker instance."""
    from app.core.memory.state_tracking import memory_tracker, MemoryStateTracker
    
    assert isinstance(memory_tracker, MemoryStateTracker)


def test_global_daily_log_writer():
    """Test global daily_log_writer instance."""
    from app.core.memory.daily_log import daily_log_writer, DailyLogWriter
    
    assert isinstance(daily_log_writer, DailyLogWriter)


def test_global_log_consolidator():
    """Test global log_consolidator instance."""
    from app.core.memory.daily_log import log_consolidator, LogConsolidator
    
    assert isinstance(log_consolidator, LogConsolidator)


def test_memory_package_exports():
    """Test memory package exports."""
    from app.core.memory import (
        get_relevant_memories,
        quality_analyzer,
        memory_tracker,
        daily_log_writer,
        log_consolidator,
        SmartMemoryRetriever,
        MemoryQualityAnalyzer,
        MemoryStateTracker,
        DailyLogWriter,
        LogConsolidator,
    )
    
    assert callable(get_relevant_memories)
    assert quality_analyzer is not None
    assert memory_tracker is not None
    assert daily_log_writer is not None
    assert log_consolidator is not None


# ============== Test Runner ==============

async def main():
    print("="*60)
    print("Phase 3 ARM64 Test Suite")
    print("="*60)
    
    result = TestResult()
    
    # Smart Retrieval Tests
    print("\n[Smart Retrieval Tests]")
    tests = [
        test_smart_retriever_init,
        test_candidate_keyword_scoring,
        test_freshness_boost,
        test_type_priority,
        test_recent_tool_filtering,
        test_keep_warnings_with_recent_tools,
        test_llm_response_parsing,
        test_llm_response_parsing_codeblock,
        test_llm_invalid_json_fallback,
    ]
    
    for test in tests:
        try:
            test()
            result.add_pass(test.__name__)
        except Exception as e:
            result.add_fail(test.__name__, str(e))
    
    # Quality Tests
    print("\n[Quality Analysis Tests]")
    tests = [
        test_quality_freshness_now,
        test_quality_freshness_old,
        test_quality_specificity_with_files,
        test_quality_specificity_vague,
        test_quality_actionability_directives,
        test_quality_actionability_descriptive,
    ]
    
    for test in tests:
        try:
            test()
            result.add_pass(test.__name__)
        except Exception as e:
            result.add_fail(test.__name__, str(e))
    
    # Async quality test
    try:
        await test_quality_overall_score()
        result.add_pass("test_quality_overall_score")
    except Exception as e:
        result.add_fail("test_quality_overall_score", str(e))
    
    # State Tracking Tests
    print("\n[State Tracking Tests]")
    tests = [
        test_state_tracker_init,
        test_state_tracker_mark_surfaced,
        test_state_tracker_mark_multiple,
        test_state_tracker_is_surfaced,
        test_state_tracker_filter_fresh,
        test_state_tracker_ttl_expiration,
        test_state_tracker_clear_thread,
        test_predictive_cache,
        test_predictive_cache_miss,
    ]
    
    for test in tests:
        try:
            test()
            result.add_pass(test.__name__)
        except Exception as e:
            result.add_fail(test.__name__, str(e))
    
    # Daily Log Tests
    print("\n[Daily Log Tests]")
    
    try:
        await test_daily_log_writer()
        result.add_pass("test_daily_log_writer")
    except Exception as e:
        result.add_fail("test_daily_log_writer", str(e))
    
    try:
        await test_log_consolidator()
        result.add_pass("test_log_consolidator")
    except Exception as e:
        result.add_fail("test_log_consolidator", str(e))
    
    tests = [
        test_log_entry_markdown,
    ]
    
    for test in tests:
        try:
            test()
            result.add_pass(test.__name__)
        except Exception as e:
            result.add_fail(test.__name__, str(e))
    
    # Global Instances Tests
    print("\n[Global Instances Tests]")
    tests = [
        test_global_smart_retriever,
        test_global_quality_analyzer,
        test_global_memory_tracker,
        test_global_daily_log_writer,
        test_global_log_consolidator,
        test_memory_package_exports,
    ]
    
    for test in tests:
        try:
            test()
            result.add_pass(test.__name__)
        except Exception as e:
            result.add_fail(test.__name__, str(e))
    
    # Summary
    success = result.summary()
    
    if success:
        print("\n✅ All Phase 3 tests passed on ARM64!")
    else:
        print(f"\n❌ {result.failed} test(s) failed")
    
    return 0 if success else 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
