import pytest
import asyncio
from app.infrastructure.database.vector import get_vector_store
from app.core.atlas import atlas_engine
from app.core.environment.controllers.mobile_controller import MobileController
from app.utils.time import utcnow

@pytest.mark.asyncio
async def test_cognitive_e2e_lifecycle():
    # 1. Environment Setup
    os.environ["EMBEDDED_MODE"] = "true"
    from app.infrastructure.database.vector.lancedb_store import LanceVectorStore
    import app.infrastructure.database.vector as vector_mod
    import tempfile
    import shutil
    
    temp_dir = tempfile.mkdtemp()
    real_store = LanceVectorStore(db_path=os.path.join(temp_dir, "e2e_lancedb"))
    
    # Bypass the global test mock
    original_get_store = vector_mod.get_vector_store
    vector_mod.get_vector_store = lambda: real_store
    vector_store = real_store
    
    # 2. Simulate Domain Learning (Skill)
    # This mimics what learn_from_trace.py does
    skill_name = "E2E_Test_Skill"
    skill_vec = [0.42] * 768
    vector_store.upsert_skill_chunks([{
        "id": skill_name,
        "name": skill_name,
        "description": "A skill created during E2E test.",
        "vector": skill_vec
    }])
    
    # Verify retrieval
    search_res = vector_store.search_skills([0.42] * 768)
    print(f"\nE2E Search Results: {search_res}")
    assert any(s["id"] == skill_name for s in search_res)
    
    # 3. Simulate Spatial Resolution (Atlas)
    # Mocking a dynamic app scenario
    bundle_id = "com.e2e.dynamic.app"
    # We clear atlas to ensure clean state
    await atlas_engine.clear_atlas()
    
    # Verify Atlas query returns empty
    apps = await atlas_engine.store.list_apps()
    assert len(apps) == 0
    
    # 4. Controller Interaction with Strategy
    # Here we audit that the controller correctly calls Atlas
    # Since we don't have a real device, we check the resolve_element logic
    # by passing a name that will trigger Atlas resolution
    
    # Mocking atlas_engine.resolve_spatial_element for this test
    original_resolve = atlas_engine.resolve_spatial_element
    try:
        async def mock_resolve(*args, **kwargs):
            return {"strategy": "search_then_click", "parameters": {"description": "E2E Mock Strategy"}, "source": "test"}
        
        atlas_engine.resolve_spatial_element = mock_resolve
        
        # This action should now return an error message containing the strategy
        # instead of a coordinate timeout error
        # Note: We use a dummy device_id
        res = await MobileController.execute(
            action="tap",
            element_name="DynamicButton",
            device_id="emulator-5554"
        )
        
        assert "dynamic app" in res.lower()
        assert "Strategy required" in res
        assert "E2E Mock Strategy" in res
        
    finally:
        atlas_engine.resolve_spatial_element = original_resolve
        vector_mod.get_vector_store = original_get_store
        shutil.rmtree(temp_dir)

import os
