from app.core.atlas.adapters.neo4j_store import Neo4jAtlasStore
from app.core.atlas.config_manager import (
    AtlasConfigManager,
    get_bundle_id,
    is_dynamic_app,
)
from app.core.atlas.engine import AtlasEngine

# Default global instance using Neo4j
atlas_engine = AtlasEngine(store=Neo4jAtlasStore())

__all__ = ["AtlasEngine", "atlas_engine", "AtlasConfigManager", "get_bundle_id", "is_dynamic_app"]
