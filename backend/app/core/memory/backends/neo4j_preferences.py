"""Neo4j implementation of preference store."""

import logging
from typing import Optional

from app.core.memory.interfaces.preferences import IPreferenceStore
from app.infrastructure.database.graph.driver import get_graph_db

logger = logging.getLogger(__name__)


class Neo4jPreferenceStore(IPreferenceStore):
    """Neo4j implementation of hierarchical preference storage."""

    async def initialize(self) -> None:
        """Initialize preference constraints."""
        driver = await get_graph_db()
        async with driver.session() as session:
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")
            await session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Preference) REQUIRE p.key IS UNIQUE")
        logger.info("Neo4jPreferenceStore: Initialized")

    async def flush(self) -> None:
        """Clear all preferences."""
        driver = await get_graph_db()
        async with driver.session() as session:
            await session.run("MATCH (p:Preference) DETACH DELETE p")
            await session.run("MATCH (u:User) DETACH DELETE u")
        logger.info("Neo4jPreferenceStore: Flushed all preferences")

    async def set_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        description: str = "",
        project_id: Optional[int] = None,
    ) -> None:
        """Set a user preference with optional project scoping."""
        driver = await get_graph_db()
        pid_val = project_id if project_id else 0

        query = """
        MERGE (u:User {id: $user_id})
        MERGE (p:Preference {key: $key})
        SET p.description = $description
        MERGE (u)-[r:PREFERS {project_id: $pid}]->(p)
        SET r.value = $value
        RETURN p
        """
        async with driver.session() as session:
            await session.run(
                query,
                user_id=user_id,
                key=key,
                value=value,
                description=description,
                pid=pid_val,
            )
            scope = f"Project {pid_val}" if pid_val else "Global"
            logger.info(f"Stored Preference ({scope}): {key}={value}")

    async def get_merged_preferences(self, user_id: str, project_id: Optional[int] = None) -> str:
        """Get merged preferences with project overrides."""
        driver = await get_graph_db()
        target_pid = project_id if project_id else 0

        query = """
        MATCH (u:User {id: $user_id})-[r:PREFERS]->(p:Preference)
        WHERE r.project_id = 0 OR r.project_id = $pid
        RETURN p.key as key, r.value as value, p.description as desc, r.project_id as pid
        ORDER BY r.project_id ASC
        """

        async with driver.session() as session:
            result = await session.run(query, user_id=user_id, pid=target_pid)
            records = await result.data()

        if not records:
            return "No specific preferences recorded."

        # Merge Logic: Project overrides Global
        final_prefs = {}
        for r in records:
            key = r["key"]
            val = r["value"]
            scope_pid = r["pid"]
            desc = r["desc"]
            final_prefs[key] = (
                f"- {key}: {val} ({desc})" + (" [Global]" if scope_pid == 0 else " [Project]")
            )

        return "\n".join(["**User Preferences:**"] + sorted(final_prefs.values()))
