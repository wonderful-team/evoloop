"""
EvoLoop Utilities Package.

Import directly from submodules: `from app.utils.id import gen_uuid`.
Do NOT add re-exports here — the old 318-line re-export caused heavy
modules (image, geometry, serialization) to load at import time,
forcing ~980 inline imports across the codebase.
"""
