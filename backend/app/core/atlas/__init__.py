from app.core.atlas.adapters.sql_store import SQLAtlasStore
from app.core.atlas.config_manager import (
    AtlasConfigManager,
    get_bundle_id,
    is_dynamic_app,
)
from app.core.atlas.engine import AtlasEngine

# Global singleton
atlas_engine = AtlasEngine(store=SQLAtlasStore())

__all__ = [
    "AtlasEngine",
    "atlas_engine",
    "AtlasConfigManager",
    "get_bundle_id",
    "is_dynamic_app",
]
