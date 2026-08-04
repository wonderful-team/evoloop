from app.core.environment.models import AwakenedState

# Global awakened state (singleton)
_awakened_state: AwakenedState | None = None


def get_awakened_state() -> AwakenedState | None:
    """
    Get the current awakened state.

    Returns None if the Agent has not been awakened yet.
    """
    return _awakened_state


def set_awakened_state(state: AwakenedState) -> None:
    """Internal setter for the awakened state."""
    global _awakened_state
    _awakened_state = state
