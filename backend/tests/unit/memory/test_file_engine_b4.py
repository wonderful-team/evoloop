"""Tests for B4: FileEngine project_roots routing."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from app.core.memory.file_engine import _FileEngine, MemoryCategory
from app.core.memory.models import MemoryEntry, MemoryType, MemoryTier, PrivacyLevel


@pytest.fixture
def engine():
    base = tempfile.mkdtemp()
    proj_root = tempfile.mkdtemp()
    engine = _FileEngine(base_dir=base, project_roots={42: proj_root})
    return engine, Path(base), Path(proj_root)


class TestFileEngineProjectRoots:
    async def test_project_roots_loaded_at_init(self, engine):
        eng, _, _ = engine
        assert 42 in eng._project_roots
        assert isinstance(eng._project_roots[42], Path)

    async def test_project_roots_empty_by_default(self):
        eng = _FileEngine(base_dir=tempfile.mkdtemp())
        assert eng._project_roots == {}

    async def test_ensure_directories_creates_project_dirs(self, engine):
        eng, _, proj_root = engine
        for cat in MemoryCategory:
            assert (proj_root / cat.value).exists()

    async def test_get_storage_path_routes_to_project_root(self, engine):
        eng, _, _ = engine
        entry = MemoryEntry(
            id="test_001",
            type=MemoryType.CONCEPT,
            title="Test Concept",
            content="test",
            project_id=42,
            created_at=datetime(2025, 1, 1),
        )
        path, category = eng._get_storage_path(entry)
        assert str(eng._project_roots[42]) in str(path)
        assert "concept" not in str(path)

    async def test_get_storage_path_uses_default_root_for_global(self, engine):
        eng, base, _ = engine
        entry = MemoryEntry(
            id="test_002",
            type=MemoryType.CONCEPT,
            title="Global Concept",
            content="test",
            project_id=0,
            created_at=datetime(2025, 1, 1),
        )
        path, category = eng._get_storage_path(entry)
        assert str(base) in str(path)

    async def test_get_storage_path_uses_default_root_for_unregistered_project(self, engine):
        eng, base, _ = engine
        entry = MemoryEntry(
            id="test_003",
            type=MemoryType.CONCEPT,
            title="Unknown Project",
            content="test",
            project_id=999,
            created_at=datetime(2025, 1, 1),
        )
        path, category = eng._get_storage_path(entry)
        assert str(base) in str(path)

    async def test_scan_includes_project_roots(self, engine):
        eng, _, proj_root = engine
        cat_dir = proj_root / "context"
        cat_dir.mkdir(parents=True, exist_ok=True)
        test_file = cat_dir / "project-concept.md"
        test_file.write_text(
            "---\n"
            'id: "proj_concept_42"\n'
            'type: "concept"\n'
            'tier: "transient"\n'
            'privacy: "team"\n'
            'title: "Project Concept"\n'
            "---\n"
            "Test content\n"
        )
        await eng._build_memory_id_index()
        assert "proj_concept_42" in eng._id_index

    async def test_memory_store_project_roots_property(self):
        from app.core.memory.store import MemoryStore
        project_roots = {1: "/tmp/proj1", 2: "/tmp/proj2"}
        store = MemoryStore(base_dir=tempfile.mkdtemp(), project_roots=project_roots)
        assert store.project_roots[1] == Path("/tmp/proj1")
        assert store.project_roots[2] == Path("/tmp/proj2")
        store.project_roots[3] = "/tmp/proj3"
        assert 3 in store.project_roots


class TestTwoTierRootPathPriority:
    """B4: TwoTierMemoryManager root_path priority (root_path > config > default)."""

    def test_root_path_takes_priority(self):
        from app.core.memory.two_tier import TwoTierMemoryManager
        from unittest.mock import MagicMock

        storage = MagicMock()
        custom_root = Path("/custom/memory/root")
        mgr = TwoTierMemoryManager(
            storage=storage,
            root_path=custom_root,
            config=None,
        )
        assert mgr.root == custom_root
        assert mgr.memory_md_path == custom_root / "MEMORY.md"

    def test_config_used_when_no_root_path(self):
        from app.core.memory.two_tier import TwoTierMemoryManager
        from unittest.mock import MagicMock, PropertyMock

        storage = MagicMock()
        config = MagicMock()
        config_root = Path("/config/memory/root")
        type(config).user_memory_root = PropertyMock(return_value=config_root)

        mgr = TwoTierMemoryManager(
            storage=storage,
            root_path=None,
            config=config,
        )
        assert mgr.root == config_root

    def test_settings_default_when_neither_provided(self):
        from app.core.memory.two_tier import TwoTierMemoryManager
        from app.core.config import settings
        from unittest.mock import MagicMock

        storage = MagicMock()
        mgr = TwoTierMemoryManager(
            storage=storage,
            root_path=None,
            config=None,
        )
        assert mgr.root == Path(settings.BRAIN_MEMORY_ROOT)

    def test_project_id_filtering(self):
        from app.core.memory.two_tier import TwoTierMemoryManager
        from unittest.mock import MagicMock

        storage = MagicMock()
        mgr = TwoTierMemoryManager(
            storage=storage,
            project_id=42,
        )
        assert mgr._project_id == 42

    async def test_get_hot_memory_custom_root(self):
        from app.core.memory.two_tier import TwoTierMemoryManager
        from unittest.mock import MagicMock, patch

        import tempfile
        custom_root = Path(tempfile.mkdtemp())

        storage = MagicMock()
        mgr = TwoTierMemoryManager(
            storage=storage,
            root_path=custom_root,
        )

        assert mgr.root == custom_root
        assert not mgr.memory_md_path.exists()

        with patch.object(mgr, 'regenerate_memory_md') as mock_regen:
            with patch.object(mgr, '_read_truncated') as mock_read:
                mock_read.return_value = "# Generated MEMORY.md"
                result = await mgr.get_hot_memory()
                assert result == "# Generated MEMORY.md"
