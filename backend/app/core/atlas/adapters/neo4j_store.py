import logging
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.infrastructure.database.graph.driver import Neo4jManager
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.models import AtlasApp

logger = logging.getLogger(__name__)


class Neo4jAtlasStore(IAtlasStore):
    """
    Handles persistence of App Atlas data into Neo4j graph database.
    Implements IAtlasStore.
    """

    async def save_app_model(self, atlas_app: AtlasApp) -> None:
        """
        Persists the entire AtlasApp into Neo4j.
        """
        driver = Neo4jManager.get_driver()
        async with driver.session() as session:
            try:
                # 1. Merge App Node
                await session.run(
                    """
                    MERGE (a:App {bundle_id: $bundle_id})
                    SET a.app_name = $app_name,
                        a.platform = $platform,
                        a.last_observed_at = datetime($last_observed_at),
                        a.version_hash = $version_hash
                    """,
                    bundle_id=atlas_app.bundle_id,
                    app_name=atlas_app.app_name,
                    platform=atlas_app.platform,
                    last_observed_at=datetime.now().isoformat(),
                    version_hash=atlas_app.version_hash
                )

                # 2. Merge State Nodes
                for state_id, state in atlas_app.states.items():
                    await session.run(
                        """
                        MATCH (a:App {bundle_id: $bundle_id})
                        MERGE (s:State {state_id: $state_id, bundle_id: $bundle_id})
                        SET s.window_title = $window_title,
                            s.elements_json = $elements_json,
                            s.screenshot_hash = $screenshot_hash
                        MERGE (a)-[:HAS_STATE]->(s)
                        """,
                        bundle_id=atlas_app.bundle_id,
                        state_id=state_id,
                        window_title=state.window_title,
                        elements_json=json.dumps([e.to_dict() for e in state.elements], ensure_ascii=False),
                        screenshot_hash=state.screenshot_hash
                    )

                # 3. Merge Transitions
                for trans in atlas_app.transitions:
                    await session.run(
                        """
                        MATCH (s1:State {state_id: $from_state, bundle_id: $bundle_id}),
                              (s2:State {state_id: $to_state, bundle_id: $bundle_id})
                        MERGE (s1)-[r:TRANSITION {
                            action_label: $action_label,
                            action_path: $action_path,
                            action_type: $action_type
                        }]->(s2)
                        """,
                        bundle_id=atlas_app.bundle_id,
                        from_state=trans.from_state,
                        to_state=trans.to_state,
                        action_label=trans.action.label,
                        action_path=trans.action.ax_path,
                        action_type=trans.action_type
                    )

                logger.info(f"Successfully saved Atlas for {atlas_app.bundle_id} to Neo4j")
            except Exception as e:
                logger.error(f"Failed to save Atlas to Neo4j for {atlas_app.bundle_id}: {e}")
                raise e

    async def get_app_summary(self, bundle_id: str, platform: str = "macos") -> Optional[Dict[str, Any]]:
        """
        Retrieves a high-level summary of the App mapping from Neo4j.
        """
        driver = Neo4jManager.get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:App {bundle_id: $bundle_id, platform: $platform})
                OPTIONAL MATCH (a)-[:HAS_STATE]->(s:State)
                RETURN a.app_name as app_name, 
                       count(s) as state_count,
                       collect({id: s.state_id, title: s.window_title}) as states
                """,
                bundle_id=bundle_id,
                platform=platform
            )
            record = await result.single()
            if not record or not record.get("app_name"):
                return None
            
            return {
                "app_name": record["app_name"],
                "bundle_id": bundle_id,
                "platform": platform,
                "state_count": record["state_count"],
                "states": record["states"]
            }

    async def get_state_detail(self, bundle_id: str, state_id: str, platform: str = "macos") -> Optional[Dict[str, Any]]:
        """
        Retrieve detailed information about a specific UI state, including its elements.
        """
        driver = Neo4jManager.get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:App {bundle_id: $bundle_id, platform: $platform})-[:HAS_STATE]->(s:State {state_id: $state_id})
                RETURN s.window_title as window_title, s.elements_json as elements_json
                """,
                bundle_id=bundle_id,
                platform=platform,
                state_id=state_id
            )
            record = await result.single()
            if not record:
                return None
            
            elements = []
            if record["elements_json"]:
                elements = json.loads(record["elements_json"])
                
            return {
                "state_id": state_id,
                "window_title": record["window_title"],
                "elements": elements
            }

    async def get_transitions_summary(self, bundle_id: str, platform: str = "macos") -> List[Dict[str, Any]]:
        """Returns all known transitions for an app."""
        driver = Neo4jManager.get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:App {bundle_id: $bundle_id, platform: $platform})-[:HAS_STATE]->(s1:State)-[r:TRANSITION]->(s2:State)
                RETURN s1.state_id as from_state,
                       r.action_label as label,
                       r.action_type as type,
                       s2.state_id as to_state
                """,
                bundle_id=bundle_id,
                platform=platform
            )
            return [dict(record) for record in await result.data()]

    async def list_apps(self) -> List[Dict[str, Any]]:
        """Returns a list of all apps that have atlas data in Neo4j."""
        driver = Neo4jManager.get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a:App)
                RETURN a.app_name as app_name, a.bundle_id as bundle_id, a.platform as platform
                ORDER BY a.app_name
                """
            )
            return [dict(record) for record in await result.data()]
