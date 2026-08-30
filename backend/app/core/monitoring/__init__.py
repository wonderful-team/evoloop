def __getattr__(name: str):
    if name == "activity_monitor":
        from app.core.monitoring.activity import activity_monitor

        return activity_monitor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
