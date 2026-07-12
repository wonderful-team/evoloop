import os
import shutil
import tempfile

import pytest

from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp, AtlasElement, AtlasState


@pytest.mark.asyncio
async def test_cognitive_e2e_lifecycle(_real_db):
    # 1. Environment Setup
    os.environ["EMBEDDED_MODE"] = "true"

    import app.infrastructure.database.vector as vector_mod
    from app.infrastructure.database.vector.lancedb_store import LanceVectorStore

    temp_dir = tempfile.mkdtemp()
    real_store = LanceVectorStore(db_path=os.path.join(temp_dir, "e2e_lancedb"))

    # Bypass the global test mock
    original_get_store = vector_mod.get_vector_store
    vector_mod.get_vector_store = lambda: real_store
    vector_store = real_store

    try:
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

        # 3. Simulate Spatial Resolution (Atlas) over the real DB
        bundle_id = "com.e2e.dynamic.app"
        await atlas_engine.clear_atlas()

        apps = await atlas_engine.store.list_apps()
        assert len(apps) == 0

        # 4. Atlas spatial-memory round-trip: save a mapped app with an
        # element carrying coordinates, then resolve it back through the
        # same engine path the mobile controller consults.
        app_model = AtlasApp(
            app_name="E2E App",
            bundle_id=bundle_id,
            platform="android",
            states={
                "main": AtlasState(
                    state_id="main",
                    window_title="Main",
                    elements=[
                        AtlasElement(
                            role="BUTTON",
                            label="DynamicButton",
                            x=120,
                            y=340,
                        )
                    ],
                )
            },
        )
        await atlas_engine.store.save_app_model(app_model)

        resolved = await atlas_engine.resolve_spatial_element(
            bundle_id, "DynamicButton", platform="android"
        )
        assert resolved == {"x": 120, "y": 340, "source": "atlas_memory"}

        # Unknown element resolves to None (no false positives)
        assert (
            await atlas_engine.resolve_spatial_element(
                bundle_id, "NoSuchButton", platform="android"
            )
            is None
        )
    finally:
        vector_mod.get_vector_store = original_get_store
        shutil.rmtree(temp_dir)
