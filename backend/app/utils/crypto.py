import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import settings

def _get_fernet_key() -> bytes:
    # Derive a static 32-byte key from settings.SECRET_KEY
    key_material = settings.SECRET_KEY.encode("utf-8")
    derived = hashlib.sha256(key_material).digest()
    return base64.urlsafe_b64encode(derived)

def encrypt_payload(data: str) -> str:
    """Encrypt a string payload using AES-256 (Fernet)."""
    f = Fernet(_get_fernet_key())
    return f.encrypt(data.encode("utf-8")).decode("utf-8")

def decrypt_payload(token: str) -> str:
    """Decrypt an encrypted payload back to string."""
    f = Fernet(_get_fernet_key())
    return f.decrypt(token.encode("utf-8")).decode("utf-8")
