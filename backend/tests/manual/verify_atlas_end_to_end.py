
import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.core.atlas import atlas_engine
from app.core.atlas.models import AtlasApp
from app.core.atlas.strategy import AtlasStrategyStore, AppStrategy, InteractionStrategy
from app.infrastructure.cache import cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AtlasEndToEnd")

async def verify_end_to_end():
    logger.info("=== Atlas End-to-End Audit & Verification ===")
    
    # 1. Setup Mock Data
    bundle_id = "com.test.audit.app"
    platform = "macos"
    
    # Ensure clean state
    await atlas_engine.clear_atlas()
    await AtlasStrategyStore.delete_strategy(bundle_id, platform)
    
    # 2. Test dynamic app classification (Controller Path)
    from app.core.atlas.config_manager import AtlasConfigManager
    await AtlasConfigManager.mark_app_dynamic(bundle_id, platform, reason="Audit test")
    
    is_dynamic = await atlas_engine.is_dynamic_app(bundle_id, platform)
    logger.info(f"Step 1: is_dynamic_app verification: {is_dynamic}")
    assert is_dynamic is True, "is_dynamic_app should return True for marked app"
    
    # 3. Test strategy retrieval (Controller Path)
    strategy_data = AppStrategy(
        bundle_id=bundle_id,
        platform=platform,
        infrastructure=[{"role": "search", "label": "Global Search", "element_category": "static_navigation_top"}],
        strategies=[
            InteractionStrategy(strategy_type="static_click", target_element="Login", parameters={"resource_id": "btn_login"})
        ]
    )
    await AtlasStrategyStore.save_strategy(strategy_data)
    
    retrieved_strategy = await atlas_engine.get_app_strategy(bundle_id, platform)
    logger.info(f"Step 2: get_app_strategy verification: {retrieved_strategy is not None}")
    assert retrieved_strategy is not None
    
    # Verify model methods (used by controllers)
    infra = retrieved_strategy.get_infrastructure_element("search")
    logger.info(f"Step 3: get_infrastructure_element verification: {infra['label'] if infra else 'None'}")
    assert infra and infra["label"] == "Global Search"
    
    strat = retrieved_strategy.get_strategy_for("Login")
    logger.info(f"Step 4: get_strategy_for verification: {strat.strategy_type if strat else 'None'}")
    assert strat and strat.strategy_type == "static_click"

    # 4. Test UI Observation Flow (Agent/Harvest Path)
    logger.info("Step 5: Simulating UI Observation (Dynamic App)...")
    event = type('Event', (), {
        'data': {
            'bundle_id': bundle_id,
            'window_title': 'Audit Window',
            'platform': platform,
            'screenshot_hash': 'h1',
            'version_hash': 'v1'
        },
        'elements': [
            {"role": "AXButton", "name": "Login", "bounds": [10, 10, 100, 30]},
            {"role": "AXTextField", "name": "Search", "bounds": [200, 10, 200, 30]}
        ]
    })()
    
    await atlas_engine.on_ui_tree_observed(event)
    
    # Verify that ONLY infrastructure was stored (since it's dynamic)
    summary = await atlas_engine.store.get_app_summary(bundle_id, platform)
    logger.info(f"Step 6: App Summary (should have 1 infra state): {len(summary.get('states', []))}")
    print(f"DEBUG: states = {summary['states']}")
    assert len(summary.get('states', [])) == 1
    assert summary['states'][0]['id'].endswith("_infra")
    
    # 5. Test Agent Tool Output
    logger.info("Step 7: Verifying Agent Tool outputs...")
    summary_md = await atlas_engine.query_app_atlas(bundle_id, platform=platform)
    logger.info(f"Summary MD preview:\n{summary_md[:200]}...")
    assert "App UI Atlas" in summary_md
    assert bundle_id in summary_md
    
    logger.info("=== Atlas End-to-End Verification PASSED ===")

if __name__ == "__main__":
    asyncio.run(verify_end_to_end())
