import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from app.core.atlas.adapters.graph_store import GraphAtlasStore
from app.core.atlas.models import AtlasApp, AtlasState, AtlasElement
from app.infrastructure.database.graph.driver import GraphManager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AtlasVerify")

async def test_atlas_integration():
    logger.info("--- Testing GraphAtlasStore Integration ---")
    settings.EMBEDDED_MODE = True
    store = GraphAtlasStore()
    
    # 1. Create App Model
    app = AtlasApp(
        app_name="TestApp",
        bundle_id="com.test.app",
        platform="macos"
    )
    
    state = AtlasState(
        state_id="main_window",
        window_title="Main Window",
        elements=[
            AtlasElement(role="button", label="OK", os_identifier="ok_btn"),
            AtlasElement(role="input", label="Name", os_identifier="name_field")
        ]
    )
    app.add_state(state)
    
    # 2. Save
    await store.save_app_model(app)
    logger.info("Saved App Model")
    
    # 3. Get Summary
    summary = await store.get_app_summary("com.test.app")
    logger.info(f"App Summary: {summary}")
    assert summary is not None
    assert summary.state_count == 1
    
    # 4. Get Detail
    detail = await store.get_state_detail("com.test.app", "main_window")
    logger.info(f"State Detail: {detail.window_title} with {len(detail.elements)} elements")
    assert len(detail.elements) == 2
    
    # 5. List Apps
    apps = await store.list_apps()
    logger.info(f"Listed Apps: {apps}")
    assert any(a.bundle_id == "com.test.app" for a in apps)
    
    # 6. Clear
    await store.clear_all_data()
    logger.info("Atlas data cleared")
    
    logger.info("Atlas integration PASSED")

if __name__ == "__main__":
    asyncio.run(test_atlas_integration())
