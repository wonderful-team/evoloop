import logging
from datetime import datetime
from typing import Any

from app.core.atlas.models import AtlasApp
from app.core.atlas.ports.store import (
    AtlasAppInfo,
    AtlasAppSummary,
    AtlasStateDetail,
    IAtlasStore,
)
from app.infrastructure.database.graph.driver import GraphManager

logger = logging.getLogger(__name__)


class GraphAtlasStore(IAtlasStore):
    """
    Graph-based Atlas Storage.
    Works with any IGraphDriver (Neo4j or FileGraph).
    """

    def __init__(self):
        logger.info("GraphAtlasStore initialized")

    async def save_app_model(self, atlas_app: AtlasApp) -> None:
        """
        Persists the entire AtlasApp into the graph database.
        """
        driver = GraphManager.get_driver()
        try:
            # 1. Upsert App Node
            await driver.upsert_node("App", "bundle_id", {
                "bundle_id": atlas_app.bundle_id,
                "app_name": atlas_app.app_name,
                "platform": atlas_app.platform,
                "last_observed_at": datetime.now().isoformat(),
                "version_hash": atlas_app.version_hash
            })

            # 2. Upsert State Nodes and link to App
            for state_id, state in atlas_app.states.items():
                await driver.upsert_node("State", "state_id", {
                    "state_id": state_id,
                    "bundle_id": atlas_app.bundle_id,
                    "window_title": state.window_title,
                    "screenshot_hash": state.screenshot_hash
                })
                
                # Link App -> State
                await driver.link_nodes(
                    "App",
                    {"bundle_id": atlas_app.bundle_id},
                    "State",
                    {"state_id": state_id},
                    "HAS_STATE",
                )

                # Link State -> UIElement
                for element in state.elements:
                    el_id = element.os_identifier or f"{state_id}_{element.label}_{element.role}"
                    props = element.model_dump()
                    props["element_id"] = el_id

                    await driver.upsert_node("UIElement", "element_id", props)
                    await driver.link_nodes(
                        "State",
                        {"state_id": state_id},
                        "UIElement",
                        {"element_id": el_id},
                        "CONTAINS",
                    )

            # 3. Upsert Transitions
            for trans in atlas_app.transitions:
                await driver.link_nodes(
                    "State",
                    {"state_id": trans.from_state},
                    "State",
                    {"state_id": trans.to_state},
                    "TRANSITION",
                    rel_props={
                        "action_label": trans.action.label,
                        "action_type": trans.action_type,
                    },
                )

            logger.info(f"Successfully saved Atlas for {atlas_app.bundle_id}")
        except Exception as e:
            logger.error(f"Failed to save Atlas for {atlas_app.bundle_id}: {e}")
            raise e

    async def get_app_summary(self, bundle_id: str, platform: str = "macos") -> AtlasAppSummary | None:
        """Retrieves a high-level summary of the App mapping."""
        driver = GraphManager.get_driver()
        apps = await driver.find_nodes("App", {"bundle_id": bundle_id, "platform": platform}, limit=1)
        if not apps:
            return None

        app = apps[0]
        states_nodes = await driver.traverse(
            "App",
            {"bundle_id": bundle_id},
            rel_type="HAS_STATE",
            target_label="State"
        )

        return AtlasAppSummary(
            app_name=app.get("app_name", "Unknown"),
            bundle_id=bundle_id,
            platform=platform,
            version_hash=app.get("version_hash", ""),
            state_count=len(states_nodes),
            states=[{"id": s["state_id"], "title": s.get("window_title", "")} for s in states_nodes]
        )

    async def get_state_detail(self, bundle_id: str, state_id: str, platform: str = "macos") -> AtlasStateDetail | None:
        """Get detail for a specific state."""
        driver = GraphManager.get_driver()
        # Find by state_id (scoped by bundle_id if possible for safety)
        nodes = await driver.find_nodes("State", {"state_id": state_id, "bundle_id": bundle_id}, limit=1)
        if not nodes:
            return None

        record = nodes[0]
        elements_nodes = await driver.traverse(
            "State",
            {"state_id": state_id},
            rel_type="CONTAINS",
            target_label="UIElement",
        )

        return AtlasStateDetail(
            state_id=state_id,
            window_title=record.get("window_title", "Unknown"),
            elements=elements_nodes,
        )

    async def get_transitions_summary(self, bundle_id: str, platform: str = "macos") -> list[dict[str, Any]]:
        """Returns all known transitions for an app."""
        driver = GraphManager.get_driver()

        # We use execute_query as it's the most efficient for multi-hop relationship retrieval
        query = """
        MATCH (a:App {bundle_id: $bundle_id, platform: $platform})-[:HAS_STATE]->(s1:State)-[r:TRANSITION]->(s2:State)
        RETURN s1.state_id as from_state,
               r.action_label as label,
               r.action_type as type,
               s2.state_id as to_state
        """
        return await driver.execute_query(query, bundle_id=bundle_id, platform=platform)

    async def list_apps(self) -> list[AtlasAppInfo]:
        """Returns a list of all apps."""
        driver = GraphManager.get_driver()
        nodes = await driver.find_nodes("App")
        return [
            AtlasAppInfo(
                app_name=n.get("app_name", "Unknown"),
                bundle_id=n["bundle_id"],
                platform=n.get("platform", "macos"),
            )
            for n in nodes
        ]

    async def clear_all_data(self) -> None:
        """Clears all Atlas data."""
        driver = GraphManager.get_driver()
        await driver.delete_nodes("App")
        await driver.delete_nodes("State")
        await driver.delete_nodes("UIElement")
        logger.warning("Atlas data cleared from graph")
