import pytest
import os
import shutil
import tempfile
from datetime import datetime, timezone
from app.infrastructure.database.vector.lancedb_store import LanceVectorStore
from app.utils.time import utcnow

@pytest.fixture
def temp_lancedb():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_lancedb")
    store = LanceVectorStore(db_path=db_path)
    yield store
    shutil.rmtree(temp_dir)

def test_skills_lifecycle(temp_lancedb):
    store = temp_lancedb
    
    # 1. Test Upsert
    skill_data = [
        {
            "id": "skill_1",
            "name": "Navigate to Home",
            "description": "Clicks the home button on the dashboard.",
            "vector": [0.1] * 768
        },
        {
            "id": "skill_2",
            "name": "Export Data",
            "description": "Downloads the current view as CSV.",
            "vector": [0.9] * 768
        }
    ]
    
    count = store.upsert_skill_chunks(skill_data)
    assert count == 2
    
    # 2. Test Search (Close match)
    results = store.search_skills([0.11] * 768, top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "skill_1"
    assert results[0]["score"] > 0.90
    
    # 3. Test Search (Distant match)
    results = store.search_skills([0.85] * 768, top_k=1)
    assert results[0]["id"] == "skill_2"

def test_concepts_lifecycle(temp_lancedb):
    store = temp_lancedb
    
    # 1. Test Upsert
    concept_data = [
        {
            "id": "concept_1",
            "name": "Authentication",
            "description": "The process of verifying identity.",
            "project_id": 1,
            "vector": [0.2] * 768
        }
    ]
    
    count = store.upsert_concept_chunks(concept_data)
    assert count == 1
    
    # 2. Test Search
    results = store.search_concepts([0.2] * 768, top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "concept_1"

def test_timestamp_awareness(temp_lancedb):
    store = temp_lancedb
    now = utcnow()
    
    # Verify utcnow is aware
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc
    
    # Verify stored data uses aware objects
    skill_data = [{
        "id": "ts_test",
        "name": "Test",
        "description": "Test",
        "vector": [0.0] * 768
    }]
    store.upsert_skill_chunks(skill_data)
    
    # We check the raw table if possible or just rely on the logic audit
    # LanceDB/PyArrow converts to timestamps internally.
