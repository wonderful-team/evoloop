import logging
import keyring
from typing import Optional

logger = logging.getLogger(__name__)


class IdentityStore:
    """
    Abstraction over OS-level secure storage (Keychain/Keyring).
    Stores sensitive tokens and keys.
    """

    SERVICE_NAME = "EvoLoop"

    @classmethod
    def save_cloud_token(cls, token: str) -> bool:
        try:
            keyring.set_password(cls.SERVICE_NAME, "cloud_token", token)
            return True
        except Exception as e:
            logger.error(f"Failed to save cloud token to keychain: {e}")
            return False

    @classmethod
    def get_cloud_token(cls) -> Optional[str]:
        try:
            return keyring.get_password(cls.SERVICE_NAME, "cloud_token")
        except Exception as e:
            logger.error(f"Failed to get cloud token from keychain: {e}")
            return None

    @classmethod
    def delete_cloud_token(cls) -> bool:
        try:
            keyring.delete_password(cls.SERVICE_NAME, "cloud_token")
            return True
        except keyring.errors.PasswordDeleteError:
            return True  # Already deleted
        except Exception as e:
            logger.error(f"Failed to delete cloud token from keychain: {e}")
            return False

    @classmethod
    def save_device_key(cls, key: str) -> bool:
        try:
            keyring.set_password(cls.SERVICE_NAME, "device_key", key)
            return True
        except Exception as e:
            logger.error(f"Failed to save device key to keychain: {e}")
            return False

    @classmethod
    def get_device_key(cls) -> Optional[str]:
        try:
            return keyring.get_password(cls.SERVICE_NAME, "device_key")
        except Exception as e:
            logger.error(f"Failed to get device key from keychain: {e}")
            return None

    @classmethod
    def save_member_id(cls, member_id: int) -> bool:
        try:
            keyring.set_password(cls.SERVICE_NAME, "member_id", str(member_id))
            return True
        except Exception as e:
            logger.error(f"Failed to save member_id to keychain: {e}")
            return False

    @classmethod
    def get_member_id(cls) -> Optional[int]:
        try:
            val = keyring.get_password(cls.SERVICE_NAME, "member_id")
            return int(val) if val else None
        except Exception as e:
            logger.error(f"Failed to get member_id from keychain: {e}")
            return None
