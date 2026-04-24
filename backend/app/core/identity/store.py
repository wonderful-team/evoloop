import json
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy import keyring to allow environment variable configuration
# This is critical for PyInstaller builds to avoid keychain prompts
_keyring = None


def _get_keyring():
    global _keyring
    if _keyring is None:
        import keyring
        _keyring = keyring
    return _keyring


def _get_token_file_path():
    """Get the path to the token storage file in embedded mode."""
    # Use app data directory for token storage
    app_data = Path.home() / "Library" / "Application Support" / "com.evoloop.app"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data / "tokens.json"


def _use_file_token_storage():
    """Check if token should be stored in local file instead of OS keychain.

    True when running as a PyInstaller bundled desktop app or when
    EVOLOOP_TOKEN_STORAGE is explicitly set to 'file'.
    """
    return settings.EVOLOOP_BUNDLED_APP or settings.EVOLOOP_TOKEN_STORAGE == "file"


def _file_storage_get(key: str) -> str | None:
    """Get a value from file-based token storage."""
    try:
        token_file = _get_token_file_path()
        if not token_file.exists():
            return None
        with open(token_file) as f:
            data = json.load(f)
        return data.get(key)
    except Exception as e:
        logger.error(f"Failed to read from file storage: {e}")
        return None


def _file_storage_set(key: str, value: str) -> bool:
    """Set a value in file-based token storage."""
    try:
        token_file = _get_token_file_path()
        data = {}
        if token_file.exists():
            with open(token_file) as f:
                data = json.load(f)
        data[key] = value
        with open(token_file, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Failed to write to file storage: {e}")
        return False


def _file_storage_delete(key: str) -> bool:
    """Delete a value from file-based token storage."""
    try:
        token_file = _get_token_file_path()
        if not token_file.exists():
            return True
        with open(token_file) as f:
            data = json.load(f)
        if key in data:
            del data[key]
        with open(token_file, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Failed to delete from file storage: {e}")
        return False


class IdentityStore:
    """
    Abstraction over OS-level secure storage (Keychain/Keyring).
    Stores sensitive tokens and keys.
    """

    @classmethod
    def save_access_token(cls, token: str) -> bool:
        if _use_file_token_storage():
            return _file_storage_set("access_token", token)
        try:
            _get_keyring().set_password(settings.SERVICE_NAME, "access_token", token)
            return True
        except Exception as e:
            logger.error(f"Failed to save access token to keychain: {e}")
            return False

    @classmethod
    def get_access_token(cls) -> str | None:
        if _use_file_token_storage():
            return _file_storage_get("access_token")
        try:
            return _get_keyring().get_password(settings.SERVICE_NAME, "access_token")
        except Exception as e:
            logger.error(f"Failed to get access token from keychain: {e}")
            return None

    @classmethod
    def delete_access_token(cls) -> bool:
        if _use_file_token_storage():
            return _file_storage_delete("access_token")
        try:
            kr = _get_keyring()
            kr.delete_password(settings.SERVICE_NAME, "access_token")
            return True
        except Exception as e:
            if "PasswordDeleteError" in type(e).__name__ or "not found" in str(e).lower():
                return True  # Already deleted
            logger.error(f"Failed to delete access token from keychain: {e}")
            return False

    @classmethod
    def save_device_key(cls, key: str) -> bool:
        if _use_file_token_storage():
            return _file_storage_set("device_key", key)
        try:
            _get_keyring().set_password(settings.SERVICE_NAME, "device_key", key)
            return True
        except Exception as e:
            logger.error(f"Failed to save device key to keychain: {e}")
            return False

    @classmethod
    def get_device_key(cls) -> str | None:
        if _use_file_token_storage():
            return _file_storage_get("device_key")
        try:
            return _get_keyring().get_password(settings.SERVICE_NAME, "device_key")
        except Exception as e:
            logger.error(f"Failed to get device key from keychain: {e}")
            return None

    @classmethod
    def save_member_id(cls, member_id: int) -> bool:
        if _use_file_token_storage():
            return _file_storage_set("member_id", str(member_id))
        try:
            _get_keyring().set_password(settings.SERVICE_NAME, "member_id", str(member_id))
            return True
        except Exception as e:
            logger.error(f"Failed to save member_id to keychain: {e}")
            return False

    @classmethod
    def get_member_id(cls) -> int | None:
        if _use_file_token_storage():
            val = _file_storage_get("member_id")
            return int(val) if val else None
        try:
            val = _get_keyring().get_password(settings.SERVICE_NAME, "member_id")
            return int(val) if val else None
        except Exception as e:
            logger.error(f"Failed to get member_id from keychain: {e}")
            return None
