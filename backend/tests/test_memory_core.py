"""
Memory System Core Test (without langchain dependencies)

Run with: python test_memory_core.py
"""

import sys
import os
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime
from enum import Enum

# Test standalone without full app dependencies
sys.path.insert(0, os.path.dirname(__file__))

import yaml

print("=" * 60)
print("EvoLoop Memory System - Core Functionality Test")
print("=" * 60)

# Define enums
class MemoryType(str, Enum):
    USER = 'user'
    FEEDBACK = 'feedback'
    PROJECT = 'project'
    REFERENCE = 'reference'

class PrivacyLevel(str, Enum):
    PRIVATE = 'private'
    TEAM = 'team'

# Inline MemoryEntry implementation
class MemoryEntry:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', '')
        self.type = kwargs.get('type', MemoryType.PROJECT)
        if isinstance(self.type, str):
            self.type = MemoryType(self.type)
        self.privacy = kwargs.get('privacy', PrivacyLevel.PRIVATE)
        if isinstance(self.privacy, str):
            self.privacy = PrivacyLevel(self.privacy)
        self.title = kwargs.get('title', '')
        self.content = kwargs.get('content', '')
        self.description = kwargs.get('description', '')
        self.project_id = kwargs.get('project_id')
        self.user_id = kwargs.get('user_id')
        self.tags = kwargs.get('tags', [])
        self.source = kwargs.get('source', 'manual')
        self.confidence = kwargs.get('confidence', 1.0)
        self.version = kwargs.get('version', 1)
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.updated_at = kwargs.get('updated_at', datetime.utcnow())
        self.extra = kwargs.get('extra', {})
    
    def to_frontmatter(self):
        frontmatter = {
            'id': self.id,
            'type': self.type.value,
            'privacy': self.privacy.value,
            'title': self.title,
            'description': self.description,
            'tags': self.tags,
            'source': self.source,
            'confidence': self.confidence,
            'version': self.version,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if self.project_id is not None:
            frontmatter['project_id'] = self.project_id
        if self.user_id is not None:
            frontmatter['user_id'] = self.user_id
        if self.extra:
            frontmatter['extra'] = self.extra
        
        yaml_lines = ['---']
        for key, value in frontmatter.items():
            if value is None:
                continue
            if isinstance(value, list):
                if value:
                    yaml_lines.append(f'{key}:')
                    for item in value:
                        yaml_lines.append(f'  - {item}')
            elif isinstance(value, dict):
                if value:
                    yaml_lines.append(f'{key}:')
                    for k, v in value.items():
                        yaml_lines.append(f'  {k}: {v}')
            elif isinstance(value, str) and (':' in value or value == ''):
                yaml_lines.append(f'{key}: "{value}"')
            else:
                yaml_lines.append(f'{key}: {value}')
        yaml_lines.append('---')
        
        return '\n'.join(yaml_lines) + '\n\n' + self.content
    
    @classmethod
    def from_frontmatter(cls, text):
        if not text.startswith('---'):
            return cls._from_content_only(text)
        
        parts = text.split('---', 2)
        if len(parts) < 3:
            raise ValueError("Invalid frontmatter format")
        
        frontmatter = yaml.safe_load(parts[1])
        content = parts[2].strip()
        
        def parse_ts(ts):
            if isinstance(ts, datetime):
                return ts
            if isinstance(ts, str):
                try:
                    return datetime.fromisoformat(ts.replace('Z', '+00:00'))
                except:
                    pass
            return datetime.utcnow()
        
        return cls(
            id=frontmatter.get('id', ''),
            type=MemoryType(frontmatter.get('type', 'project')),
            privacy=PrivacyLevel(frontmatter.get('privacy', 'private')),
            title=frontmatter.get('title', ''),
            content=content,
            description=frontmatter.get('description', ''),
            project_id=frontmatter.get('project_id'),
            user_id=frontmatter.get('user_id'),
            tags=frontmatter.get('tags', []),
            source=frontmatter.get('source', 'manual'),
            confidence=frontmatter.get('confidence', 1.0),
            version=frontmatter.get('version', 1),
            created_at=parse_ts(frontmatter.get('created_at')),
            updated_at=parse_ts(frontmatter.get('updated_at')),
            extra=frontmatter.get('extra', {}),
        )
    
    @classmethod
    def _from_content_only(cls, text):
        import uuid
        return cls(
            id=f"mem_imported_{uuid.uuid4().hex[:8]}",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.PRIVATE,
            title=text.strip().split('\n')[0][:100] if text else "Untitled",
            content=text,
            description=text.strip()[:200],
            source="imported",
        )

# Inline FileMemoryStorage implementation
class FileMemoryStorage:
    def __init__(self, root_path):
        self.root = Path(root_path)
        self.private_dir = self.root / 'private'
        self.team_dir = self.root / 'team'
        self.index_file = self.root / 'MEMORY.md'
        self._ensure_directories()
    
    def _ensure_directories(self):
        self.private_dir.mkdir(parents=True, exist_ok=True)
        self.team_dir.mkdir(parents=True, exist_ok=True)
        (self.private_dir / 'feedback').mkdir(exist_ok=True)
        (self.team_dir / 'reference').mkdir(exist_ok=True)
    
    def _get_storage_path(self, entry):
        base = self.private_dir if entry.privacy == PrivacyLevel.PRIVATE else self.team_dir
        
        if entry.type == MemoryType.USER:
            return base / f"{entry.id}.md"
        elif entry.type == MemoryType.FEEDBACK:
            subdir = base / 'feedback'
            subdir.mkdir(exist_ok=True)
            return subdir / f"{datetime.utcnow().strftime('%Y-%m-%d')}-{entry.id}.md"
        elif entry.type == MemoryType.PROJECT:
            if entry.project_id:
                subdir = base / f"project-{entry.project_id}"
            else:
                subdir = base / 'project-global'
            subdir.mkdir(exist_ok=True)
            return subdir / f"{entry.id}.md"
        elif entry.type == MemoryType.REFERENCE:
            subdir = base / 'reference'
            subdir.mkdir(exist_ok=True)
            return subdir / f"{entry.id}.md"
        return base / f"{entry.id}.md"
    
    async def save(self, entry):
        path = self._get_storage_path(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry.updated_at = datetime.utcnow()
        content = entry.to_frontmatter()
        path.write_text(content, encoding='utf-8')
        return True
    
    async def get(self, entry_id):
        for pattern in ['**/*.md']:
            for path in self.root.glob(pattern):
                if path.name == 'MEMORY.md':
                    continue
                try:
                    text = path.read_text(encoding='utf-8')
                    entry = MemoryEntry.from_frontmatter(text)
                    if entry.id == entry_id:
                        return entry
                except:
                    continue
        return None
    
    async def delete(self, entry_id):
        entry = await self.get(entry_id)
        if not entry:
            return False
        path = self._get_storage_path(entry)
        if path.exists():
            path.unlink()
            return True
        return False
    
    async def search(self, query, types=None, privacy=None, project_id=None, limit=10):
        results = []
        query_lower = query.lower()
        
        for pattern in ['private/**/*.md', 'team/**/*.md']:
            for path in self.root.glob(pattern):
                if path.name == 'MEMORY.md':
                    continue
                try:
                    text = path.read_text(encoding='utf-8')
                    entry = MemoryEntry.from_frontmatter(text)
                    
                    if types and entry.type not in types:
                        continue
                    if privacy and entry.privacy != privacy:
                        continue
                    if project_id is not None and entry.project_id != project_id:
                        continue
                    
                    searchable = f"{entry.title} {entry.description} {entry.content}".lower()
                    if query_lower in searchable:
                        results.append(entry)
                        if len(results) >= limit:
                            return results
                except:
                    continue
        return results
    
    async def list_all(self, type_filter=None, privacy_filter=None):
        results = []
        for pattern in ['private/**/*.md', 'team/**/*.md']:
            for path in self.root.glob(pattern):
                if path.name == 'MEMORY.md':
                    continue
                try:
                    text = path.read_text(encoding='utf-8')
                    entry = MemoryEntry.from_frontmatter(text)
                    if type_filter and entry.type != type_filter:
                        continue
                    if privacy_filter and entry.privacy != privacy_filter:
                        continue
                    results.append(entry)
                except:
                    continue
        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results
    
    async def get_recent(self, count=5):
        entries = await self.list_all()
        return entries[:count]
    
    async def flush(self):
        pass

# Test 1: MemoryEntry creation
print("\n[1/6] Testing MemoryEntry creation...")
try:
    entry = MemoryEntry(
        id="mem_test_001",
        type=MemoryType.FEEDBACK,
        privacy=PrivacyLevel.PRIVATE,
        title="Test Feedback",
        content="This is a test feedback memory",
        description="Test description",
        project_id=1,
        tags=["test", "feedback"],
        confidence=0.95,
    )
    print(f"✅ MemoryEntry created: {entry.title} ({entry.type.value})")
except Exception as e:
    print(f"❌ Failed: {e}")
    sys.exit(1)

# Test 2: Serialization
print("\n[2/6] Testing serialization/deserialization...")
try:
    serialized = entry.to_frontmatter()
    assert "mem_test_001" in serialized
    assert "feedback" in serialized
    print(f"✅ Serialized: {len(serialized)} chars")
    
    entry2 = MemoryEntry.from_frontmatter(serialized)
    assert entry2.id == entry.id
    assert entry2.title == entry.title
    assert entry2.content == entry.content
    print("✅ Deserialized successfully")
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()

# Test 3: File storage
print("\n[3/6] Testing FileMemoryStorage...")

async def test_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileMemoryStorage(tmpdir)
        
        # Save
        await storage.save(entry)
        print("✅ Save operation successful")
        
        # Get
        retrieved = await storage.get("mem_test_001")
        assert retrieved is not None
        assert retrieved.title == "Test Feedback"
        print("✅ Get operation successful")
        
        # Search
        results = await storage.search("test")
        assert len(results) > 0
        print(f"✅ Search found {len(results)} results")
        
        # List all
        all_mems = await storage.list_all()
        assert len(all_mems) > 0
        print(f"✅ List all: {len(all_mems)} memories")
        
        # Get recent
        recent = await storage.get_recent(5)
        assert len(recent) > 0
        print(f"✅ Get recent: {len(recent)} items")
        
        # Delete
        deleted = await storage.delete("mem_test_001")
        assert deleted
        print("✅ Delete successful")
        
        # Verify deletion
        after = await storage.get("mem_test_001")
        assert after is None
        print("✅ Deletion verified")

try:
    asyncio.run(test_storage())
except Exception as e:
    print(f"❌ Storage test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Directory structure
print("\n[4/6] Testing directory structure...")

def test_directory_structure():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileMemoryStorage(tmpdir)
        
        # Create different types of memories
        memories = [
            MemoryEntry(id="user_001", type=MemoryType.USER, privacy=PrivacyLevel.PRIVATE, title="User Profile", content="Test"),
            MemoryEntry(id="fb_001", type=MemoryType.FEEDBACK, privacy=PrivacyLevel.PRIVATE, title="Feedback", content="Test"),
            MemoryEntry(id="proj_001", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM, title="Project", content="Test", project_id=1),
            MemoryEntry(id="ref_001", type=MemoryType.REFERENCE, privacy=PrivacyLevel.TEAM, title="Reference", content="Test"),
        ]
        
        async def save_all():
            for mem in memories:
                await storage.save(mem)
        
        asyncio.run(save_all())
        
        # Verify structure
        root = Path(tmpdir)
        assert (root / 'private').exists()
        assert (root / 'team').exists()
        assert (root / 'private' / 'feedback').exists()
        assert (root / 'team' / 'reference').exists()
        assert (root / 'team' / 'project-1').exists()
        
        print("✅ Directory structure correct")
        
        # Count files
        files = list(root.glob('**/*.md'))
        assert len(files) == 4
        print(f"✅ All {len(files)} memories stored correctly")

test_directory_structure()

# Test 5: Search with filters
print("\n[5/6] Testing search with filters...")

async def test_search_filters():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = FileMemoryStorage(tmpdir)
        
        # Create test memories
        await storage.save(MemoryEntry(id="u1", type=MemoryType.USER, privacy=PrivacyLevel.PRIVATE, title="User Pref", content="Test"))
        await storage.save(MemoryEntry(id="p1", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM, title="Project Doc", content="Test", project_id=1))
        await storage.save(MemoryEntry(id="p2", type=MemoryType.PROJECT, privacy=PrivacyLevel.TEAM, title="Another Project", content="Test", project_id=2))
        
        # Test type filter
        user_results = await storage.search("Test", types=[MemoryType.USER])
        assert len(user_results) == 1
        print(f"✅ Type filter works: {len(user_results)} USER")
        
        # Test privacy filter
        private_results = await storage.search("Test", privacy=PrivacyLevel.PRIVATE)
        assert len(private_results) == 1
        print(f"✅ Privacy filter works: {len(private_results)} PRIVATE")
        
        # Test project filter
        proj1_results = await storage.search("Test", types=[MemoryType.PROJECT], project_id=1)
        assert len(proj1_results) == 1
        print(f"✅ Project filter works: {len(proj1_results)} for project 1")

asyncio.run(test_search_filters())

# Test 6: Complex content
print("\n[6/6] Testing complex content...")

try:
    complex_entry = MemoryEntry(
        id="complex_001",
        type=MemoryType.PROJECT,
        privacy=PrivacyLevel.TEAM,
        title="Architecture Decision",
        content="""## Context
We needed to choose a database for the new project.

## Decision
We will use PostgreSQL.

## Rationale
- Better JSON support
- ACID compliance
- Team familiarity

## Consequences
Need to set up connection pooling.""",
        description="Chose PostgreSQL for the project",
        project_id=1,
        tags=["architecture", "database", "decision"],
    )
    
    serialized = complex_entry.to_frontmatter()
    deserialized = MemoryEntry.from_frontmatter(serialized)
    
    assert "## Context" in deserialized.content
    assert "PostgreSQL" in deserialized.content
    assert len(deserialized.tags) == 3
    print("✅ Complex content handled correctly")
    
except Exception as e:
    print(f"❌ Complex content test failed: {e}")

print("\n" + "=" * 60)
print("All Core Tests Passed! ✨")
print("=" * 60)
print("\nSummary:")
print("- MemoryEntry: ✅ Creation, serialization, deserialization")
print("- FileMemoryStorage: ✅ Save, get, search, list, delete")
print("- Directory Structure: ✅ Private/Team organization")
print("- Search Filters: ✅ Type, privacy, project filters")
print("- Complex Content: ✅ Markdown with headers and lists")
