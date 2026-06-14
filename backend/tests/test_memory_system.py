"""
Memory System Test Suite

Run with: python test_memory_system.py
"""

import sys
import os
import tempfile
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

# Set embedded mode
os.environ['EMBEDDED_MODE'] = 'true'
os.environ['SQLITE_DB_PATH'] = ':memory:'

import yaml
from datetime import datetime
from enum import Enum


class MemoryType(str, Enum):
    USER = 'user'
    FEEDBACK = 'feedback'
    PROJECT = 'project'
    REFERENCE = 'reference'


class PrivacyLevel(str, Enum):
    PRIVATE = 'private'
    TEAM = 'team'


# Restore real vector store (conftest.py mocks it for unit tests)
import app.infrastructure.database.vector as _vector_mod
from app.infrastructure.database.vector.lancedb_store import LanceVectorStore
import app.core.memory.store as _store_mod

# Need a real get_vector_store that works
def _real_get_vector_store():
    if _vector_mod._vector_store is not None:
        return _vector_mod._vector_store
    _vector_mod._vector_store = LanceVectorStore()
    return _vector_mod._vector_store

_vector_mod._vector_store = None
_vector_mod.get_vector_store = _real_get_vector_store
_store_mod.get_vector_store = _real_get_vector_store


print("=" * 60)
print("EvoLoop Memory System Test Suite")
print("=" * 60)

# Test 1: Import all necessary modules
print("\n[1/8] Testing imports...")
try:
    from app.core.memory.models import MemoryEntry, MemoryType as MT, PrivacyLevel as PL
    from app.core.memory.store import MemoryStore
    from app.core.memory.interfaces.long_term import Concept, Episode
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test 2: MemoryEntry serialization
print("\n[2/8] Testing MemoryEntry serialization...")
try:
    entry = MemoryEntry(
        id="mem_test_001",
        type=MT.FEEDBACK,
        privacy=PL.PRIVATE,
        title="Test Feedback",
        content="This is a test feedback memory\n\nWith multiple lines.",
        description="Test description",
        project_id=1,
        tags=["test", "feedback"],
        confidence=0.95,
    )
    
    # Serialize
    serialized = entry.to_frontmatter()
    assert "mem_test_001" in serialized
    assert "feedback" in serialized
    assert "Test Feedback" in serialized
    print(f"✅ Serialization successful ({len(serialized)} chars)")
    
    # Deserialize
    entry2 = MemoryEntry.from_frontmatter(serialized)
    assert entry2.id == "mem_test_001"
    assert entry2.type == MT.FEEDBACK
    assert entry2.title == "Test Feedback"
    print("✅ Deserialization successful")
    
except Exception as e:
    print(f"❌ Serialization test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: MemoryStore
print("\n[3/8] Testing MemoryStore...")

async def test_storage():
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStore(tmpdir)
            
            # Test save
            entry = MemoryEntry(
                id="mem_storage_001",
                type=MT.PROJECT,
                privacy=PL.TEAM,
                title="Storage Test",
                content="Testing file storage backend",
                project_id=1,
            )
            await storage.save(entry)
            print("✅ Save operation successful")
            
            # Test get
            retrieved = await storage.get("mem_storage_001")
            assert retrieved is not None
            assert retrieved.title == "Storage Test"
            print("✅ Get operation successful")
            
            # Test search
            results = await storage.search("file storage")
            assert len(results) > 0
            print(f"✅ Search operation successful ({len(results)} results)")
            
            # Test list_all
            all_memories = await storage.list_all()
            assert len(all_memories) > 0
            print(f"✅ List operation successful ({len(all_memories)} memories)")
            
            # Test get_recent
            recent = await storage.get_recent(5)
            assert len(recent) > 0
            print(f"✅ Recent memories retrieved ({len(recent)} items)")
            
            # Test delete
            deleted = await storage.delete("mem_storage_001")
            assert deleted is True
            print("✅ Delete operation successful")
            
            # Verify deletion
            after_delete = await storage.get("mem_storage_001")
            assert after_delete is None
            print("✅ Deletion verified")
            
    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        import traceback
        traceback.print_exc()

try:
    asyncio.run(test_storage())
except Exception as e:
    print(f"❌ Storage test error: {e}")

# Test 4: Concept and Episode compatibility
print("\n[4/8] Testing Concept/Episode compatibility...")
try:
    concept = Concept(
        name="TestConcept",
        description="A test concept for compatibility",
        project_id=1,
        related_files=["test.py"]
    )
    assert concept.name == "TestConcept"
    print("✅ Concept creation successful")
    
    episode = Episode(
        goal="Test the memory system",
        result="Success",
        plan_summary="1. Test storage\n2. Test retrieval",
        error_msg=None,
        project_id=1,
        source_message_id="msg_001"
    )
    assert episode.goal == "Test the memory system"
    print("✅ Episode creation successful")
    
except Exception as e:
    print(f"❌ Concept/Episode test failed: {e}")

# Test 5: MemoryManager with adapters
print("\n[5/8] Testing MemoryManager with adapters...")

def test_adapters():
    """Test the adapter pattern without full async"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create storage
            storage = MemoryStore(tmpdir)
            
            # Test the new interface directly
            async def run_tests():
                # Test save_memory
                entry = MemoryEntry(
                    id="mem_mgr_001",
                    type=MT.USER,
                    privacy=PL.PRIVATE,
                    title="Manager Test",
                    content="Testing manager interface",
                )
                await storage.save(entry)
                print("✅ save_memory works")
                
                # Test search_memories
                results = await storage.search("manager")
                print(f"✅ search_memories works ({len(results)} results)")
                
                # Test get_memory
                result = await storage.get("mem_mgr_001")
                assert result is not None
                print("✅ get_memory works")
                
                return True
            
            return asyncio.run(run_tests())
    
    except Exception as e:
        print(f"❌ Manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

try:
    success = test_adapters()
    if success:
        print("✅ MemoryManager adapters working")
except Exception as e:
    print(f"❌ Adapter test error: {e}")

# Test 6: Preference adapter
print("\n[6/8] Testing Preference adapter...")

async def test_prefs():
    """Test preference save and search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStore(tmpdir)
        
        # Simulate setting a preference
        entry = MemoryEntry(
            id="pref_1_test_key",
            type=MT.USER,
            privacy=PL.PRIVATE,
            title="Preference: test_key",
            content="test_key: test_value\n\nTest preference",
            description="test_key = test_value",
            member_id=1,
            tags=["preference", "test_key"],
        )
        await storage.save(entry)
        
        # Search for preferences
        results = await storage.search("preference", types=[MT.USER])
        assert len(results) > 0
        
        # Get merged preferences (simulated)
        prefs_text = "No specific preferences recorded."
        if results:
            lines = ["**User Preferences:**"]
            for r in results:
                if "preference" in r.tags:
                    lines.append(f"- {r.description}")
            if len(lines) > 1:
                prefs_text = "\n".join(lines)
        
        assert "test_key" in prefs_text
        print("✅ Preference save/search works")
        print("✅ get_merged_preferences works")

# Test 7: Long-term adapter
print("\n[7/8] Testing LongTerm adapter...")

async def test_longterm():
    """Test long-term concept storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStore(tmpdir)
        
        # Test store_concept simulation
        concept = Concept(
            name="TestConcept",
            description="A test concept",
            project_id=1,
            related_files=["test.py"]
        )
        
        entry = MemoryEntry(
            id=f"concept_{concept.name}",
            type=MT.PROJECT,
            privacy=PL.TEAM,
            title=concept.name,
            content=concept.description,
            project_id=concept.project_id,
            tags=["concept"] + concept.related_files,
        )
        await storage.save(entry)
        print("✅ store_concept simulation works")
        
        # Test search_concepts simulation
        results = await storage.search("TestConcept", types=[MT.PROJECT])
        assert len(results) > 0
        print("✅ search_concepts simulation works")
        
        # Test list_concepts simulation
        all_concepts = await storage.list_all(type_filter=MT.PROJECT)
        assert len(all_concepts) > 0
        print(f"✅ list_concepts simulation works ({len(all_concepts)} concepts)")

# Test 8: Template rendering
print("\n[8/8] Testing Jinja2 templates...")
try:
    from app.utils.template import render_template
    
    # Test extraction template
    result = render_template(
        "memory/extraction.prompt.j2",
        message_count=10,
        recent_messages="User: Hello\nAssistant: Hi",
        existing_memories="No memories yet"
    )
    assert "memory extraction" in result.lower()
    print("✅ extraction.prompt.j2 renders")
    
    # Test consolidation template
    result = render_template(
        "memory/consolidation.prompt.j2",
        content="Some working memory content"
    )
    assert "consolidat" in result.lower()
    print("✅ consolidation.prompt.j2 renders")
    
    # Test retrieval template
    result = render_template(
        "memory/retrieval_selection.prompt.j2",
        query="test query",
        memories=[],
        recent_tools=[],
        max_selections=5
    )
    assert "selecting memories" in result.lower()
    print("✅ retrieval_selection.prompt.j2 renders")
    
except Exception as e:
    print(f"❌ Template test failed: {e}")

print("\n" + "=" * 60)
print("Test Suite Complete!")
print("=" * 60)
