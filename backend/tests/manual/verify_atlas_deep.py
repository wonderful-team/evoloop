import asyncio
import logging
from dataclasses import dataclass
from typing import List, Dict, Any

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("AtlasDeepVerify")

@dataclass
class MockUIEvent:
    data: Dict[str, Any]
    elements: List[Dict[str, Any]]

async def verify_atlas_deep():
    """
    Deep-dive verification of the Atlas Cognitive Engine.
    Covers: Ingestion, Multi-state Mapping, Transitions, and Agent-level Retrieval.
    """
    from app.core.atlas.engine import AtlasEngine
    from app.core.atlas.adapters.graph_store import GraphAtlasStore
    
    logger.info("=== Starting Atlas Deep-Dive Verification ===")
    
    # Initialize Engine
    engine = AtlasEngine(store=GraphAtlasStore())
    await engine.clear_atlas() # Start clean
    
    bundle_id = "com.deep.verify.app"
    platform = "macos"
    
    # 1. Simulate First Observation (Home Screen)
    logger.info("Step 1: Mapping Home Screen...")
    event_home = MockUIEvent(
        data={"bundle_id": bundle_id, "window_title": "Home", "platform": platform, "screenshot_hash": "hash_home"},
        elements=[
            {"label": "Login", "role": "AXButton", "os_identifier": "btn_login", "rect": [10, 10, 50, 20]},
            {"label": "Help", "role": "AXButton", "os_identifier": "btn_help", "rect": [100, 10, 50, 20]}
        ]
    )
    await engine.on_ui_tree_observed(event_home)
    
    # 2. Simulate Second Observation (Login Screen) - triggers transition mapping later
    logger.info("Step 2: Mapping Login Screen...")
    event_login = MockUIEvent(
        data={"bundle_id": bundle_id, "window_title": "Login", "platform": platform, "screenshot_hash": "hash_login"},
        elements=[
            {"label": "Username", "role": "AXTextField", "os_identifier": "txt_user", "rect": [50, 50, 200, 30]},
            {"label": "Submit", "role": "AXButton", "os_identifier": "btn_submit", "rect": [50, 100, 100, 30]}
        ]
    )
    await engine.on_ui_tree_observed(event_login)
    
    # 3. Manually Link Transition (Simulating Agent action or heuristic link)
    # The current engine relies on explicit transition saving via the store if not automated yet
    from app.core.atlas.models import AtlasApp, AtlasTransition, AtlasElement
    app_model = AtlasApp(bundle_id=bundle_id, app_name="Deep Verify App", platform=platform)
    # Get state IDs from engine's generator for consistency
    home_id = engine._generate_state_id(bundle_id, "Home")
    login_id = engine._generate_state_id(bundle_id, "Login")
    
    app_model.transitions.append(AtlasTransition(
        from_state=home_id,
        to_state=login_id,
        action=AtlasElement(label="Click Login", role="AXButton"),
        action_type="click"
    ))
    await engine.store.save_app_model(app_model)
    logger.info("Step 3: Manually linked Home -> Login transition.")

    # 4. Verification: App Directory
    logger.info("Step 4: Verifying App Directory...")
    apps_list = await engine.list_apps()
    logger.info(f"Directory Output:\n{apps_list}")
    assert "Deep Verify App" in apps_list
    
    # 5. Verification: App Summary
    logger.info("Step 5: Verifying App Summary (Agent Tool Output)...")
    summary = await engine.query_app_atlas(bundle_ids=bundle_id)
    logger.info(f"Summary Output:\n{summary}")
    assert "Known States (2)" in summary
    assert "Home" in summary
    assert "Login" in summary
    assert "TRANSITION" in summary or "Click Login" in summary
    
    # 6. Verification: State Detail
    logger.info("Step 6: Verifying State Detail (Agent Tool Output)...")
    # Note: query_app_atlas uses the first bundle_id if state_id is provided
    detail = await engine.query_app_atlas(bundle_ids=[bundle_id], state_id=home_id)
    logger.info(f"Detail Output (Home):\n{detail}")
    assert "Login" in detail # Button label
    assert "Help" in detail # Button label
    assert "AXButton" in detail

    logger.info("=== Atlas Deep-Dive Verification PASSED ===")

if __name__ == "__main__":
    asyncio.run(verify_atlas_deep())
