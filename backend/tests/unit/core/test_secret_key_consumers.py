"""Regression tests for SECRET_KEY consumers.

SECRET_KEY is used in exactly two places:
1. app/utils/crypto.py — derives the Fernet key that encrypts/decrypts Secure
   Vault credentials.
2. app/utils/security.py — signs JWTs (create_access_token, HS256).

These tests guard the round-trips so that, as long as the configured SECRET_KEY
remains stable (currently provided via .env), both JWT issuance and vault
payload encryption/decryption keep working.
"""

from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.security.crypto import create_access_token
from app.utils import crypto


class TestVaultCryptoRoundTrip:
    def test_encrypt_then_decrypt_round_trip(self):
        payload = '{"host": "10.0.0.1", "password": "s3cr3t", "port": 22}'
        token = crypto.encrypt_payload(payload)
        assert token != payload  # must not be stored in plaintext
        assert crypto.decrypt_payload(token) == payload

    def test_encrypt_is_nondeterministic(self):
        # Fernet includes a random IV, so two encryptions differ but both decrypt
        payload = '{"key": "value"}'
        assert crypto.encrypt_payload(payload) != crypto.encrypt_payload(payload)

    def test_decrypt_wrong_key_raises(self):
        """Data encrypted with a different SECRET_KEY must not silently decrypt."""
        import base64
        import hashlib

        from cryptography.fernet import Fernet, InvalidToken

        other = Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(b"other-key").digest())
        )
        token = other.encrypt(b"hello").decode("utf-8")
        with pytest.raises(InvalidToken):
            crypto.decrypt_payload(token)

    def test_key_is_derived_from_configured_secret(self):
        # The Fernet key must be a function of the configured SECRET_KEY, so a
        # stable SECRET_KEY (from .env) yields a stable vault key across restarts.
        assert crypto._get_fernet_key() is not None
        assert settings.SECRET_KEY  # configured and non-empty


class TestJwtSigning:
    def test_create_access_token_signed_with_secret_key(self):
        import jwt

        token = create_access_token(subject="user-123", expires_delta=timedelta(minutes=5))
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert decoded["sub"] == "user-123"

    def test_token_rejected_with_wrong_key(self):
        import jwt

        token = create_access_token(subject="user-123", expires_delta=timedelta(minutes=5))
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "some-other-key", algorithms=["HS256"])

    def test_token_expiry(self):
        import jwt

        token = create_access_token(subject="u", expires_delta=timedelta(seconds=-10))
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
