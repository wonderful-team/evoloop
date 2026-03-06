"""
[DEPRECATED] — This file is a compatibility stub.

The Mirror Session Manager has been moved to:
  app.core.environment.controllers.mirror_session

Please update all imports to use the new location.
"""
# Backward-compatible re-export
from app.core.environment.controllers.mirror_session import MirrorSession, MirrorSessionManager, mirror_manager  # noqa: F401

__all__ = ["MirrorSession", "MirrorSessionManager", "mirror_manager"]
