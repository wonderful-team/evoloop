from app.core.atlas.engine import AtlasEngine
from app.core.atlas.adapters.neo4j_store import Neo4jAtlasStore

# Default global instance using Neo4j
atlas_engine = AtlasEngine(store=Neo4jAtlasStore())

__all__ = ["AtlasEngine", "atlas_engine"]
