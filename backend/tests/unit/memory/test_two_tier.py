"""
Unit tests for Two-Tier Memory Architecture (Phase 4).

Tests hot/cold memory separation, budget system, and regeneration.

Run with: pytest tests/unit/memory/test_two_tier.py -v
"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from unittest.mock import MagicMock


class TestSectionBudget:
    """Tests for SectionBudget data class."""
    
    def test_section_budget_creation(self):
        """Test that SectionBudget can be created."""
        from app.core.memory.schemas import SectionBudget
        
        budget = SectionBudget(name="architecture", lines=25)
        
        assert budget.name == "architecture"
        assert budget.lines == 25
        assert budget.used == 0
        assert budget.remaining == 25
        assert not budget.overflow
    
    def test_section_budget_with_usage(self):
        """Test SectionBudget with usage tracking."""
        from app.core.memory.schemas import SectionBudget
        
        budget = SectionBudget(name="decisions", lines=25, used=20)
        
        assert budget.used == 20
        assert budget.remaining == 5
        assert not budget.overflow
    
    def test_section_budget_overflow(self):
        """Test SectionBudget overflow detection."""
        from app.core.memory.schemas import SectionBudget
        
        budget = SectionBudget(name="patterns", lines=25, used=30, overflow=True)
        
        assert budget.overflow
        assert budget.remaining == -5


class TestMemorySection:
    """Tests for MemorySection data class."""
    
    def test_memory_section_creation(self):
        """Test that MemorySection can be created."""
        from app.core.memory.two_tier import MemorySection
        
        section = MemorySection(
            name="architecture",
            title="Architecture",
            budget=25,
        )
        
        assert section.name == "architecture"
        assert section.title == "Architecture"
        assert len(section.entries) == 0
    
    def test_memory_section_to_markdown_empty(self):
        """Test markdown generation with no entries."""
        from app.core.memory.two_tier import MemorySection
        
        section = MemorySection(
            name="architecture",
            title="Architecture",
            budget=25,
        )
        
        markdown = section.to_markdown()
        
        assert "## Architecture" in markdown
        assert "- **" not in markdown  # No entries
    
    def test_memory_section_to_markdown_with_entries(self):
        """Test markdown generation with entries."""
        from app.core.memory.two_tier import MemorySection
        
        section = MemorySection(
            name="decisions",
            title="Key Decisions",
            budget=25,
            entries=[
                {"title": "Use PostgreSQL", "description": "For data consistency"},
                {"title": "Use Redis", "description": "For caching"},
            ],
        )
        
        markdown = section.to_markdown()
        
        assert "## Key Decisions" in markdown
        assert "Use PostgreSQL" in markdown
        assert "For data consistency" in markdown
        assert "Use Redis" in markdown
    
    def test_memory_section_overflow_indicator(self):
        """Test overflow indicator in markdown."""
        from app.core.memory.two_tier import MemorySection
        
        section = MemorySection(
            name="patterns",
            title="Patterns",
            budget=2,
            entries=[
                {"title": f"Pattern {i}", "description": f"Desc {i}"}
                for i in range(5)
            ],
        )
        
        markdown = section.to_markdown(max_lines=2)
        
        assert "Pattern 0" in markdown
        assert "Pattern 1" in markdown
        assert "and 3 more in cold memory" in markdown


class TestTwoTierMemoryManagerInit:
    """Tests for TwoTierMemoryManager initialization."""
    
    def test_default_initialization(self):
        """Test that manager initializes with defaults."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        
        assert manager.MAX_TOTAL_LINES == 200
        assert manager.MAX_TOTAL_BYTES == 25 * 1024
        assert "architecture" in manager.DEFAULT_BUDGETS
        assert manager.DEFAULT_BUDGETS["architecture"] == 25
    
    def test_custom_budgets(self):
        """Test that custom budgets can be set."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        manager.budgets["architecture"] = 50
        
        assert manager.budgets["architecture"] == 50


class TestMemoryLifespan:
    """Tests for type-specific memory lifespan."""
    
    def test_permanent_memory_types(self):
        """Test that PROJECT and USER memories don't decay."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        from app.core.memory.models import MemoryType
        
        manager = TwoTierMemoryManager(MagicMock())
        
        # Architecture (PROJECT) - should be permanent
        freshness = manager._calculate_freshness(MemoryType.PROJECT, 365)
        assert freshness == 1.0
        
        # User preferences - should be permanent
        freshness = manager._calculate_freshness(MemoryType.USER, 365)
        assert freshness == 1.0
    
    def test_decaying_memory_types(self):
        """Test that FEEDBACK and REFERENCE memories decay."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        from app.core.memory.models import MemoryType
        
        manager = TwoTierMemoryManager(MagicMock())
        
        # Feedback - 30 day lifespan
        freshness_new = manager._calculate_freshness(MemoryType.FEEDBACK, 0)
        assert freshness_new == 1.0
        
        freshness_old = manager._calculate_freshness(MemoryType.FEEDBACK, 30)
        assert freshness_old == 0.0
        
        # Reference - 7 day lifespan
        freshness_week = manager._calculate_freshness(MemoryType.REFERENCE, 7)
        assert freshness_week == 0.0
    
    def test_partial_decay(self):
        """Test partial decay calculation."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        from app.core.memory.models import MemoryType
        
        manager = TwoTierMemoryManager(MagicMock())
        
        # Halfway through 30-day lifespan
        freshness = manager._calculate_freshness(MemoryType.FEEDBACK, 15)
        assert freshness == 0.5


class TestBudgetRedistribution:
    """Tests for budget redistribution algorithm."""
    
    def test_no_redistribution_needed(self):
        """Test when all sections are within budget."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        
        sections = {
            "architecture": {"title": "Architecture", "entries": [{}, {}]},  # 2/25
            "decisions": {"title": "Decisions", "entries": [{}, {}]},      # 2/25
        }
        
        result = manager._apply_budgets(sections)
        
        assert len(result["architecture"]["entries"]) == 2
        assert len(result["decisions"]["entries"]) == 2
        assert not result["architecture"]["overflow"]
    
    def test_redistribution_to_overflow(self):
        """Test unused budget redistribution to overflowing sections."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        
        # One section way over budget, another way under
        sections = {
            "architecture": {
                "title": "Architecture",
                "entries": [{"title": f"Entry {i}"} for i in range(30)]  # 30/25 = overflow
            },
            "decisions": {
                "title": "Decisions",
                "entries": [{"title": "One entry"}]  # 1/25 = lots of room
            },
        }
        
        result = manager._apply_budgets(sections)
        
        # Architecture should get some of decisions' unused budget
        arch_entries = len(result["architecture"]["entries"])
        assert arch_entries > 25  # Got extra from decisions
        assert arch_entries <= 30  # But not all


class TestMemoryMdGeneration:
    """Tests for MEMORY.md generation."""
    
    def test_generate_default_content(self):
        """Test default content generation."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        content = manager._generate_default_content()
        
        assert "# Project Memory" in content
        assert "Architecture" in content
        assert "Key Decisions" in content
    
    def test_generate_memory_md(self):
        """Test full MEMORY.md generation."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        
        sections = {
            "architecture": {
                "title": "Architecture",
                "entries": [
                    {"title": "Microservices", "description": "Service-oriented"},
                ],
                "overflow": False,
            },
            "decisions": {
                "title": "Key Decisions",
                "entries": [
                    {"title": "Use PostgreSQL", "description": "Reliable"},
                ],
                "overflow": False,
            },
        }
        
        content = manager._generate_memory_md(sections)
        
        assert "# Project Memory" in content
        assert "## Architecture" in content
        assert "Microservices" in content
        assert "## Key Decisions" in content
        assert "Use PostgreSQL" in content


class TestMemoryMdParsing:
    """Tests for MEMORY.md parsing."""
    
    def test_parse_empty_memory_md(self):
        """Test parsing empty or minimal content."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        content = "# Project Memory\n\n## Architecture\n"
        
        sections = manager._parse_memory_md(content)
        
        assert "architecture" in sections
        assert len(sections["architecture"]["entries"]) == 0
    
    def test_parse_memory_md_with_entries(self):
        """Test parsing MEMORY.md with entries."""
        from app.core.memory.two_tier import TwoTierMemoryManager
        
        manager = TwoTierMemoryManager(MagicMock())
        content = """# Project Memory

## Architecture

- **Microservices**: Service-oriented architecture
- **Monolith**: Alternative approach

## Key Decisions

- **Use PostgreSQL**: For data consistency
"""
        
        sections = manager._parse_memory_md(content)
        
        assert "architecture" in sections
        assert len(sections["architecture"]["entries"]) == 2
        assert sections["architecture"]["entries"][0]["title"] == "Microservices"
        assert "key_decisions" in sections or "decisions" in sections


class TestIntegrationWithMemoryManager:
    """Tests for integration with MemoryManager using MemoryContainer."""

    @pytest.fixture(autouse=True)
    def mock_db_session(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.scalars = AsyncMock()
        
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        
        self.patcher = patch("app.core.memory.file_engine.session_scope", return_value=mock_session_ctx)
        self.patcher.start()
        yield
        self.patcher.stop()
    
    @pytest.mark.asyncio
    async def test_memory_manager_get_hot_memory(self):
        """Test MemoryManager.get_hot_memory() method."""
        from app.core.memory import MemoryContainer, MemoryConfig
        
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        try:
            manager = container.memory_manager
            hot_memory = await manager.get_hot_memory()
            
            # Should return string (possibly default content)
            assert isinstance(hot_memory, str)
            assert "# Project Memory" in hot_memory or "No memories" in hot_memory
        finally:
            await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_memory_manager_search_cold_memory(self):
        """Test MemoryManager.search_cold_memory() method."""
        from app.core.memory import MemoryContainer, MemoryConfig
        
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        try:
            manager = container.memory_manager
            # Search should work even with empty storage
            results = await manager.search_cold_memory("test", max_results=5)
            
            assert isinstance(results, list)
        finally:
            await container.shutdown()
    
    @pytest.mark.asyncio
    async def test_memory_manager_regenerate_memory_md(self):
        """Test MemoryManager.regenerate_memory_md() method."""
        from app.core.memory import MemoryContainer, MemoryConfig
        
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        try:
            manager = container.memory_manager
            # Should not raise exception
            await manager.regenerate_memory_md()
        finally:
            await container.shutdown()
