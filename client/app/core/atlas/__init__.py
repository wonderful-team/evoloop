from app.core.atlas.config_manager import AtlasConfigManager, get_bundle_id, is_dynamic_app
from app.core.atlas.engine import AtlasEngine

# Client-only: Atlas disabled (use cloud API)
atlas_engine = AtlasEngine(store=None)

__all__ = ["AtlasEngine", "atlas_engine", "AtlasConfigManager", "get_bundle_id", "is_dynamic_app"]
