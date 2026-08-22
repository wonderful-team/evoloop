"""Security policy package for EvoLoop.

This package consolidates cross-cutting security rules (path safety, command
sandboxing, secrets redaction, authorization policy evaluation, etc.) while
keeping framework wiring and business orchestration in their respective domains.

Submodules are intentionally **not** imported at package level to avoid heavy
dependencies and circular imports during startup. Callers should import the
specific module they need, e.g.:

    from app.core.security.path import is_path_safe
    from app.core.security.command import is_dangerous_command
"""
