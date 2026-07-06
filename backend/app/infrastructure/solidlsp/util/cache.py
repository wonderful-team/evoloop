import logging
import pickle
from typing import Any

log = logging.getLogger(__name__)


def load_cache(path: str, version: Any) -> Any | None:
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except (FileNotFoundError, EOFError, pickle.UnpicklingError):
        return None

    if not isinstance(data, dict) or "__cache_version" not in data:
        log.info("Cache is outdated (expected version %s). Ignoring cache at %s", version, path)
        return None
    saved_version = data["__cache_version"]
    if saved_version != version:
        log.info("Cache is outdated (expected version %s, got %s). Ignoring cache at %s", version, saved_version, path)
        return None
    return data["obj"]


def load_pickle(path: str) -> Any | None:
    """Simple pickle loader for legacy migrations"""
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        log.warning("Failed to load pickle from %s: %s", path, e)
        return None


def save_cache(path: str, version: Any, obj: Any) -> None:
    data = {"__cache_version": version, "obj": obj}
    try:
        with open(path, "wb") as f:
            pickle.dump(data, f)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        log.warning("Failed to save cache to %s: %s", path, e)
